import test from 'node:test';
import assert from 'node:assert/strict';
import { UploadSlot } from '../static/upload-slot.mjs';

function deferredSender() {
  const requests = [];
  const send = (file, progress) => {
    let resolve, reject;
    const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
    const request = { file, promise, resolve, reject, progress, aborted: false,
      abort() { this.aborted = true; } };
    requests.push(request);
    return request;
  };
  return { send, requests };
}

test('Motion: older success cannot replace the newly selected CSV', async () => {
  const { send, requests } = deferredSender();
  const slot = new UploadSlot(send);
  const old = slot.select({ name: 'old.csv' });
  const latest = slot.select({ name: 'new.csv' });
  assert.equal(requests[0].aborted, true);
  requests[1].resolve({ token: 'new-token' });
  await latest;
  requests[0].resolve({ token: 'old-token' });
  await old;
  assert.equal(slot.data.token, 'new-token');
  assert.equal(slot.file.name, 'new.csv');
});

test('Motion: stale errors and progress cannot overwrite current upload state', async () => {
  const { send, requests } = deferredSender();
  const slot = new UploadSlot(send);
  const old = slot.select({ name: 'old.csv' });
  const latest = slot.select({ name: 'new.csv' });
  requests[1].progress(60);
  requests[0].progress(99);
  requests[0].reject(Error('old failed'));
  await old;
  assert.equal(slot.error, null);
  assert.equal(slot.progress, 60);
  requests[1].resolve({ token: 'new' });
  await latest;
  assert.equal(slot.data.token, 'new');
});

test('clearing a CSV invalidates an upload that is still finishing', async () => {
  const { send, requests } = deferredSender();
  const slot = new UploadSlot(send);
  const old = slot.select({ name: 'old.csv' });
  await slot.select(null);
  requests[0].resolve({ token: 'old' });
  await old;
  assert.equal(slot.data, null);
  assert.equal(slot.file, null);
});

test('a real current upload failure is visible and does not reuse old data', async () => {
  const { send, requests } = deferredSender();
  const slot = new UploadSlot(send);
  const pending = slot.select({ name: 'bad.csv' });
  requests[0].reject(Error('missing time column'));
  await pending;
  assert.equal(slot.data, null);
  assert.equal(slot.error, 'missing time column');
});
