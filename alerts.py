#!/usr/bin/env python3
"""Send an iMessage (and a Mac notification) once for anything that goes over the spend limit.

Rules match the dashboard's Warnings panel:
  - a session costing over the limit in total
  - a project spending over the limit in one day
  - a model spending over the limit in one day (all projects together)
Run after export_usage.py. Recipient lives in alert.conf (not committed: the repo is public).
  python3 alerts.py --selftest   check the rules
  python3 alerts.py --test       send one test message
"""
import collections, csv, json, os, subprocess, sys, datetime as dt

LIMIT_GBP = 10.0
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, 'notified.json')
CONF = os.path.join(HERE, 'alert.conf')
RECENT_DAYS = 2  # only alert on today and yesterday, so old history never floods you


def read(name):
    with open(os.path.join(HERE, name)) as fh:
        return list(csv.DictReader(fh))


def find_alerts(usage, sessions, rate, today):
    """Return {id: message} for everything over the limit that is recent."""
    out = {}
    since = (today - dt.timedelta(days=RECENT_DAYS - 1)).isoformat()
    gbp = lambda usd: usd * rate
    for s in sessions:
        cost = gbp(float(s['cost_usd']))
        if cost > LIMIT_GBP and s['start'][:10] >= since:
            what = ' / '.join(x for x in (s.get('name'), s['label']) if x) or 'a session'
            out['session:' + s['session']] = f"Session '{what}' in {s['project']} (started {s['start'][11:16]}) has cost £{cost:.2f}"
    for kind in ('project', 'model'):
        days = collections.defaultdict(float)
        for r in usage:
            days[(r['hour'][:10], r[kind])] += float(r['cost_usd'])
        for (day, name), usd in days.items():
            cost = gbp(usd)
            if cost > LIMIT_GBP and day >= since:
                label = name.capitalize() if kind == 'model' else name
                out[f'{kind}:{name}:{day}'] = f"{kind.capitalize()} {label} has spent £{cost:.2f} on {day}"
    return out


def imessage(to, text):
    script = ('on run argv\n'
              '  tell application "Messages"\n'
              '    set svc to 1st account whose service type = iMessage\n'
              '    send (item 2 of argv) to participant (item 1 of argv) of svc\n'
              '  end tell\n'
              'end run')
    subprocess.run(['osascript', '-e', script, to, text], check=True, timeout=30)


def mac_notification(text):
    subprocess.run(['osascript', '-e', 'on run argv\ndisplay notification (item 1 of argv) with title "Claude spend alert"\nend run', text], timeout=10)


def send(text):
    mac_notification(text)
    to = open(CONF).read().strip() if os.path.exists(CONF) else ''
    if to:
        imessage(to, text)


def main():
    rate = float(read('fx.csv')[0]['usd_to_gbp'])
    alerts = find_alerts(read('usage.csv'), read('sessions.csv'), rate, dt.date.today())
    sent = set(json.load(open(STATE))) if os.path.exists(STATE) else set()
    new = [k for k in alerts if k not in sent]
    if new:
        lines = [alerts[k] for k in sorted(new)]
        send('Claude Code spend over £%d (API list prices):\n- %s\nDashboard: Claude Code token burn rate' % (LIMIT_GBP, '\n- '.join(lines)))
        sent.update(new)
        json.dump(sorted(sent), open(STATE, 'w'))
    print('alerts', len(alerts), 'new', len(new))


def selftest():
    usage = [
        {'hour': '2026-11-07T09', 'project': 'a', 'model': 'fable', 'cost_usd': '9'},
        {'hour': '2026-11-07T10', 'project': 'a', 'model': 'fable', 'cost_usd': '6'},   # a: $15 = £11.25 -> alert
        {'hour': '2026-11-07T10', 'project': 'b', 'model': 'opus', 'cost_usd': '5'},    # b: £3.75, opus £3.75 -> none
        {'hour': '2026-11-01T10', 'project': 'c', 'model': 'opus', 'cost_usd': '50'},   # too old -> none
    ]
    sessions = [
        {'session': 's1', 'start': '2026-11-07T09:05', 'project': 'a', 'name': 'Graphify run', 'label': '/graphify', 'cost_usd': '14'},  # £10.50 -> alert
        {'session': 's2', 'start': '2026-11-07T09:05', 'project': 'a', 'label': '', 'cost_usd': '13'},          # £9.75 -> none
    ]
    got = find_alerts(usage, sessions, 0.75, dt.date(2026, 11, 7))
    assert set(got) == {'session:s1', 'project:a:2026-11-07', 'model:fable:2026-11-07'}, got
    assert '£10.50' in got['session:s1'] and "'Graphify run / /graphify' in a" in got['session:s1']
    assert '£11.25' in got['project:a:2026-11-07']
    print('selftest ok')


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        selftest()
    elif '--test' in sys.argv:
        send('Test from your iMac: Claude Code spend alerts are working. You will get a message like this when anything goes over £10.')
        print('test sent')
    else:
        main()
