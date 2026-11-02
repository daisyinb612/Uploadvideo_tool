"""Upload exports with ephemeral SSH authentication; credentials are never saved."""
import base64, json, os, shlex, subprocess, tempfile
from pathlib import Path
from config import SERVER_HOST, SERVER_HOME, SERVER_DIR, SERVER_UID, SERVER_GID

def sync_exports(paths, password):
    if not password or '\n' in password:
        raise ValueError('请输入服务器密码')
    host = SERVER_HOST
    with tempfile.TemporaryDirectory(prefix='viewpair-ssh-') as temp:
        askpass = Path(temp) / 'askpass'
        askpass.write_text('#!/usr/bin/env python3\nimport os\nprint(os.environ["VIEWPAIR_SSH_PASSWORD"])\n')
        askpass.chmod(448)
        env = dict(os.environ, SSH_ASKPASS=str(askpass), SSH_ASKPASS_REQUIRE='force', DISPLAY='viewpair', VIEWPAIR_SSH_PASSWORD=password)
        options = ['-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15', '-o', 'NumberOfPasswordPrompts=1', '-o', 'PreferredAuthentications=password,keyboard-interactive,publickey']

        def ssh(command, data=None):
            r = subprocess.run(['ssh', *options, host, command], input=data, capture_output=True, text=True, env=env, timeout=120)
            if r.returncode:
                raise RuntimeError('服务器操作失败：' + r.stderr[-700:])
            return r.stdout.strip()
        remote = ssh('mktemp -d '+shlex.quote(SERVER_HOME+'/viewpair-export.XXXXXXXX'))
        if not remote.startswith(SERVER_HOME+'/viewpair-export.'):
            raise RuntimeError('服务器暂存路径异常')
        try:
            r = subprocess.run(['scp', *options, *map(str, paths), host + ':' + remote + '/'], capture_output=True, text=True, env=env, timeout=3600)
            if r.returncode:
                raise RuntimeError('上传失败：' + r.stderr[-700:])
            data = base64.b64encode(json.dumps({'source': remote, 'names': [p.name for p in paths], 'directory':str(SERVER_DIR),'uid':SERVER_UID,'gid':SERVER_GID}).encode()).decode()
            script = "import base64,json,pathlib,shutil,os,hashlib\np=json.loads(base64.b64decode(PAYLOAD)); dest=pathlib.Path(p['directory']); files=[(pathlib.Path(p['source'])/n,dest/n) for n in p['names']]\nassert all(not b.exists() for a,b in files), '服务器存在同名文件，未覆盖'\ncreated=[]\ntry:\n for a,b in files:\n  with b.open('xb') as out:\n   created.append(b)\n   with a.open('rb') as inp: shutil.copyfileobj(inp,out)\n  os.chmod(b,0o644);os.chown(b,p['uid'],p['gid'])\n  with a.open('rb') as f: original=hashlib.file_digest(f,'sha256').hexdigest()\n  with b.open('rb') as f: copied=hashlib.file_digest(f,'sha256').hexdigest()\n  assert original==copied,'服务器校验失败'\n for a,b in files:\n  link=pathlib.Path('/mnt/skill/public')/b.name\n  if os.path.lexists(link):\n   assert link.resolve()==b.resolve(),'公网存在同名文件，未覆盖'\n  else:\n   os.symlink(str(b),str(link));created.append(link)\n print(json.dumps([str(b) for a,b in files]))\nexcept:\n for b in reversed(created):b.unlink(missing_ok=True)\n raise\n".replace('PAYLOAD', repr(data))
            result = ssh('sudo -S -p ' + shlex.quote('') + ' python3 -c ' + shlex.quote(script), password + '\n')
            return json.loads(result)
        finally:
            try:
                ssh('rm -rf -- ' + shlex.quote(remote))
            except Exception:
                pass
