const STREAMING = {stream: true};

export async function readLines(response, cb, newline="\n") {
    var reader = response.body.getReader();
    try {
        var buffer = '';
        var decoder = new TextDecoder('utf-8');
        for (;;) {
            var iteration = await reader.read();
            if (iteration.done) {
                return iteration.value;
            }
            var chunks = decoder.decode(iteration.value, STREAMING).split(newline);
            buffer += chunks[0];
            for (var i = 1; i < chunks.length; i++) {
                cb(buffer);
                buffer = chunks[i];
            }
        }
    } finally {
        reader.releaseLock();
    }
}
