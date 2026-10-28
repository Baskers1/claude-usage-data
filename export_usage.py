#!/usr/bin/env python3
"""Export Claude Code token usage from ~/.claude/projects to usage.csv + fx.csv.

Run hourly by launchd (com.baskers.claude-usage). `--selftest` checks the pricing maths.
Costs are API list prices (USD) per request; a Max plan isn't billed per token.
"""
import collections, csv, datetime as dt, glob, json, os, sys, urllib.request

HOME = os.path.expanduser('~')
PROJECTS = os.path.join(HOME, '.claude', 'projects')
OUT = os.path.dirname(os.path.abspath(__file__))
DAYS = 90

# USD per MTok: input, 5m cache write, cache read, output. Source: platform.claude.com/docs/en/about-claude/pricing (28 Oct 2026)
PRICES = {
    'fable-5-1': (10, 12.5, 0.25, 50), 'mythos-5-1': (10, 12.5, 0.25, 50),
    'fable-5': (10, 12.5, 1, 50), 'mythos-5': (10, 12.5, 1, 50),
    'opus-5-5': (4, 5, 0.20, 20), 'opus-5': (5, 6.25, 0.50, 25),
    'opus-4-8': (5, 6.25, 0.50, 25), 'opus-4-7': (5, 6.25, 0.50, 25),
    'opus-4-6': (5, 6.25, 0.50, 25), 'opus-4-5': (5, 6.25, 0.50, 25),
    'opus-4-1': (15, 18.75, 1.5, 75), 'opus-4': (15, 18.75, 1.5, 75),
    'sonnet-5-5': (2, 2.5, 0.10, 10), 'sonnet-5': (2, 2.5, 0.20, 10),
    'sonnet-4-6': (3, 3.75, 0.30, 15), 'sonnet-4-5': (3, 3.75, 0.30, 15), 'sonnet-4': (3, 3.75, 0.30, 15),
    'haiku-5-5': (0.10, 0.125, 0.01, 0.50), 'haiku-4-5': (1, 1.25, 0.10, 5), 'haiku-3-5': (0.8, 1, 0.08, 4),
}
HAIKU55_LONG = (0.50, 0.625, 0.05, 2.50)  # prompt over 100k tokens


def price_key(model):
    m = (model or '').lower().replace('.', '-').replace('_', '-')
    hits = [k for k in PRICES if k in m]
    return max(hits, key=len) if hits else None  # longest match: opus-5-5 must not price as opus-5


def cost_usd(model, inp, out, cw, cr):
    k = price_key(model)
    if not k:
        return None
    p = PRICES[k]
    if k == 'haiku-5-5' and inp + cw + cr > 100_000:
        p = HAIKU55_LONG
    return (inp * p[0] + cw * p[1] + cr * p[2] + out * p[3]) / 1e6


def family(model):
    k = price_key(model) or 'other'
    return k.split('-')[0]


def project_name(folder):
    if 'scratch-workspaces' in folder:
        return 'cowork-scratch'
    if folder.startswith('-private-var'):
        return 'temp'
    prefix = '-Users-baskersimac'
    if not folder.startswith(prefix):
        return folder.strip('-') or 'other'
    rest = folder[len(prefix):]
    if rest.startswith('--'):
        return '.' + rest[2:]  # a dot-folder such as ~/.claude
    return rest[1:] or 'home'


def export():
    cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=DAYS)
    seen, agg = set(), collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0.0])
    for path in glob.glob(os.path.join(PROJECTS, '*', '**', '*.jsonl'), recursive=True):
        if os.path.getmtime(path) < cut.timestamp():
            continue
        proj = project_name(os.path.relpath(path, PROJECTS).split(os.sep)[0])
        with open(path, errors='ignore') as fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                m = d.get('message')
                if not isinstance(m, dict) or not m.get('usage') or not d.get('timestamp'):
                    continue
                model = m.get('model') or ''
                if model.startswith('<'):
                    continue
                key = (m.get('id'), d.get('requestId'))
                if key[0] and key in seen:
                    continue
                seen.add(key)
                t = dt.datetime.fromisoformat(d['timestamp'].replace('Z', '+00:00'))
                if t < cut:
                    continue
                u = m['usage']
                i, o = u.get('input_tokens') or 0, u.get('output_tokens') or 0
                cw, cr = u.get('cache_creation_input_tokens') or 0, u.get('cache_read_input_tokens') or 0
                a = agg[(t.astimezone().strftime('%Y-%m-%dT%H'), proj, family(model))]
                a[0] += i; a[1] += o; a[2] += cw; a[3] += cr; a[4] += 1
                a[5] += cost_usd(model, i, o, cw, cr) or 0
    with open(os.path.join(OUT, 'usage.csv'), 'w', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['hour', 'project', 'model', 'input_tokens', 'output_tokens', 'cache_write_tokens', 'cache_read_tokens', 'requests', 'cost_usd'])
        for (h, p, f), a in sorted(agg.items()):
            w.writerow([h, p, f, *a[:5], round(a[5], 4)])
    return len(agg)


def fx():
    try:
        with urllib.request.urlopen('https://api.frankfurter.dev/v1/latest?base=USD&symbols=GBP', timeout=20) as r:
            j = json.load(r)
        rate = float(j['rates']['GBP'])
        with open(os.path.join(OUT, 'fx.csv'), 'w') as fh:
            fh.write(f"date,usd_to_gbp\n{j['date']},{rate}\n")
    except Exception as e:  # keep the last fx.csv if the feed is down
        print('fx failed:', e, file=sys.stderr)


def selftest():
    assert price_key('claude-opus-5-5') == 'opus-5-5'
    assert price_key('claude-opus-5') == 'opus-5'
    assert price_key('claude-haiku-4-5-20251001') == 'haiku-4-5'
    assert price_key('claude-opus-4.1') == 'opus-4-1'
    assert price_key('mystery') is None and cost_usd('mystery', 1, 1, 1, 1) is None
    # Opus 5.5: 1M of each field = 4 + 20 + 5 + 0.20
    assert abs(cost_usd('claude-opus-5-5', 10**6, 10**6, 10**6, 10**6) - 29.2) < 1e-9
    # Haiku 5.5 long-context tier switches above 100k prompt tokens
    assert abs(cost_usd('claude-haiku-5-5', 50_000, 0, 0, 0) - 0.005) < 1e-12
    assert abs(cost_usd('claude-haiku-5-5', 150_000, 0, 0, 0) - 0.075) < 1e-12
    assert family('claude-sonnet-5-5') == 'sonnet' and family('x') == 'other'
    assert project_name('-Users-baskersimac') == 'home'
    assert project_name('-Users-baskersimac--claude') == '.claude'
    assert project_name('-Users-baskersimac--claude-skills') == '.claude-skills'
    assert project_name('-Users-baskersimac-Obsidian-second-brain') == 'Obsidian-second-brain'
    assert project_name('-Users-baskersimac-Library-Application-Support-Claude-scratch-workspaces-x') == 'cowork-scratch'
    assert project_name('-private-var-folders-kz') == 'temp'
    print('selftest ok')


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        selftest()
    else:
        print('rows', export())
        fx()
