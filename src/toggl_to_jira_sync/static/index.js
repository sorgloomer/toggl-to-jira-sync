Vue.component("sync-row", {
    template: `
        <div class="sync-entry">
            <div>{{ row?.toggl?.time_start }} [{{ row?.actions?.length }}] - {{row?.toggl?.comment}}</div>
        </div>
    `,
    props: ['row'],
});
Vue.component("sync-day", {
    template: `
        <div class="sync-day">
            <div class="sync-day-headline">
                <span class="icon icon-loading" v-if="day.loading"></span>
                <span class="icon icon-collapse" v-if="!day.loading" v-on:click="toggleExpand()"><span></span></span>
                <span>{{ calendarDay(day?.date) ?? "unknown day" }}</span>
                <button
                    type="button"
                    class="btn"
                    v-bind:class="(day?.actions?.length ? 'btn-primary' : 'btn-secondary') + ' ' + (day?.loading ? 'disabled' : '')"
                    v-bind:disabled="day?.loading"
                    v-on:click="executeSync()"
                >{{ day?.actions?.length }} differences</button>
                <span class="details">
                </span>
            </div>
            <div>
                <div v-if="expanded">
                    <div v-for="row in day.rows">
                        <sync-row v-bind:row="row"></sync-row>
                    </div>
                </div>
            </div>
        </div>
    `,
    props: ['day'],
    data: () => ({ expanded: false }),
    methods: {
        toggleExpand() {
            this.expanded = !this.expanded;
        },
        executeSync() {
            if (this.day.loading) {
                return;
            }
            this.day.loading = true;
            spawn(async () => {
                try {
                    await _doSyncDay(this.day);
                } catch (e) {
                    this.day.error = String(e);
                } finally {
                    this.day.loading = false;
                }
                enqueueDayUpdate(this.day);
            });
        }
    }
});

function calendarDay(m) {
    return m?.calendar(null,{
        lastDay : '[Yesterday]',
        sameDay : '[Today]',
        nextDay : '[Tomorrow]',
        lastWeek : '[last] dddd',
        nextWeek : 'dddd',
        sameElse : 'L'
    });
}

Vue.component("sync-app", {
    template: `
        <div class="sync-app">
            <div>sync-app</div>
            <div v-for="day in days">
                <sync-day v-bind:day="day"></sync-day>
            </div>
        </div>
    `,
    props: ['days'],
});

async function main() {
    var app = new Vue({
        el: "#vue-app",
        template: `<sync-app v-bind:days="days"></sync-app>`,
        data: {
            days: [],
        },
    });

    var now = moment();
    var today = now.clone().startOf('day');
    for (var i = 0; i < 3; i++) {
        var loop_day = today.clone().add(-i, 'days');
        app.days.push(makeDay(loop_day));
    }
}

function makeDay(date) {
    var result = {
        date: date.clone(),
        loading: true,
        error: null,
    };
    enqueueDayUpdate(result);
    return result;
}


var updateQueue = Promise.resolve();

function enqueueDayUpdate(day) {
    day.loading = true;
    updateQueue = updateQueue.then(() => spawn(() => _doUpdateDay(day)));
}

async function _doFetchDay(day) {
    var {min, max} = getDayRange(day);
    var resp = await fetch(`/api/diff/get?min=${encodeURIComponent(min)}&max=${encodeURIComponent(max)}`);
    if (!resp.ok) {
        throw new Error(await resp.text());
    }
    return await resp.json();
}

async function _doSyncDay(day) {
    var {min, max} = getDayRange(day);
    var resp = await fetch(`/api/diff/sync?min=${encodeURIComponent(min)}&max=${encodeURIComponent(max)}`, {method:"post"});
    if (!resp.ok) {
        throw new Error(await resp.text());
    }
    return await resp.json();
}

function getDayRange(day) {
    var min = day.date.format();
    var max = day.date.clone().add(1, 'days').format();
    return {min, max};
}

async function _doUpdateDay(day) {
    try {
        var data = await _doFetchDay(day);
        Object.assign(day, data);
    } catch(e) {
        day.error = String(e);
    } finally {
        day.loading = false;
    }
}

window.addEventListener("load", () => {
    main().catch(console.error);
});


function spawn(fn) {
    return new Promise(resolve => resolve(fn())).catch(console.error).catch(noop);
}

function noop() {}
