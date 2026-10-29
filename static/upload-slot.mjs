/** One selected file. Only the newest request may update slot state. */
export class UploadSlot {
  constructor(send, changed = () => {}) {
    this.send = send;
    this.changed = changed;
    this.version = 0;
    this.data = null;
    this.file = null;
    this.request = null;
    this.pending = Promise.resolve();
  }

  select(file) {
    const version = ++this.version;
    if (this.request) this.request.abort();
    this.file = file;
    this.data = null;
    this.error = null;
    this.progress = 0;
    this.changed(this);
    if (!file) {
      this.pending = Promise.resolve();
      return this.pending;
    }
    const request = this.send(file, progress => {
      if (version !== this.version) return;
      this.progress = progress;
      this.changed(this);
    });
    this.request = request;
    this.pending = request.promise.then(data => {
      if (version !== this.version) return;
      this.data = data;
      this.progress = 100;
      this.changed(this);
    }).catch(error => {
      if (version !== this.version) return;
      this.error = error.message;
      this.changed(this);
    }).finally(() => {
      if (version === this.version) this.request = null;
    });
    return this.pending;
  }
}
