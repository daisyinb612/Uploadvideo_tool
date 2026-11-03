"""Coffee participant identifiers. Labels are UI-only; filenames use stable IDs."""
COFFEE_ROLES = [
    {'value': 'teacher', 'name': '老师'},
    {'value': 'student1_qianxinrui', 'name': '钱馨蕊'},
    {'value': 'student2_liuqingxin', 'name': '刘清心'},
    {'value': 'student3_yuanhongtao', 'name': '袁宏涛'},
    {'value': 'student4_sunyitian', 'name': '孙轶添'},
    {'value': 'student5_caojiayou', 'name': '曹佳佑'},
    {'value': 'student6_chenweiyin', 'name': '陈威寅'},
    {'value': 'student7_chenborui', 'name': '陈博睿'},
    {'value': 'student8_xieyuxin', 'name': '谢瑜欣'},
    {'value': 'student9_weilingzhi', 'name': '魏凌志'},
    {'value': 'student10_dingxiaoxia', 'name': '丁筱夏'},
]


def normalize_role(project, value):
    if not isinstance(project, str) or project.strip().lower() != 'coffee':
        return value
    for role in COFFEE_ROLES:
        if value in (role['value'], role['name'], role['value'] + ' · ' + role['name']):
            return role['value']
    raise ValueError('coffee 项目请选择 teacher 或名单中的学生')
