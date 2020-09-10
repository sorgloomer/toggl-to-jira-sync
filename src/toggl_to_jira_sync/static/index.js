import { spawn } from './utils.js';
import { makeDay } from './components.js';

async function main() {
    var app = new Vue({
        el: "#vue-app",
        template: `
            <sync-app
                v-bind:days="days"
                v-on:more-days="moreDays()"
            ></sync-app>
        `,
        data: {
            days: [],
        },
        methods: {
            moreDays() {
                for (var i = 0; i < 3; i++) {
                    addDay();
                }
            }
        }
    });

    var now = moment();
    var today = now.clone().startOf('day');
    var dayCounter = 0;

    function addDay() {
        var loop_day = today.clone().add(dayCounter--, 'days');
        app.days.push(makeDay(loop_day));
    }

    for (var i = 0; i < 10; i++) {
        addDay();
    }
}

window.addEventListener("load", () => {
    spawn(main);
});
