export function spawn(fn) {
    return new Promise(resolve => resolve(fn())).catch(console.error).catch(noop);
}

export function noop() {}


export class Queue {
    constructor(options) {
        this.queue = [];
        this.running = 0;
        this.processing = Promise.resolve();
        this.workers = options?.workers ?? 1;
    }

    async submit(fn, priority=false) {
        var item = new QueueItem(fn);
        if (priority) {
            this.queue.unshift(item);
        } else {
            this.queue.push(item);
        }
        this.process().catch(console.error);
        return item.promise;
    }

    async process() {
        if (this.running >= this.workers) {
            return;
        }
        this.running++;
        try {
            for (;;) {
                var item = this.queue.shift();
                if (item == null) {
                    return;
                }
                await item.process();
            }
        } finally {
            this.running--;
        }
    }
}

class QueueItem {
    constructor(fn) {
        this.fn = fn;
        this.promise = new Promise((resolve, reject) => {
            this.resolve = resolve;
            this.reject = reject;
        });
    }
    process() {
        return Promise.resolve().then(this.fn).then(this.resolve, this.reject);
    }
}
