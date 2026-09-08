"""Supplementary Chinese previews of byte-identical, already accepted pages."""
from pathlib import Path
import datetime
import hashlib
import json
from playwright.sync_api import sync_playwright

C = Path('/public/home/accl15ptg7/run_R08_R10')
OUT = C / 'R10_readable_previews_001'
R = Path('/public/home/accl15ptg7/auto_trace/perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003/artifacts/R10/continuation_001')
accepted = json.loads((R / 'validation/BROWSER_ACCEPTANCE.json').read_text())
assert accepted['status'] == 'complete' and accepted['network_attempt_count'] == 0
font = json.loads((OUT / 'FONT_INSTALLATION.json').read_text())
assert font['status'] == 'complete'

def rec(path):
    data = path.read_bytes()
    return {'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

attempts = []
results = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path='/root/r08_r10_browser_tools/chromium-1234/chrome-linux64/chrome',
        headless=True, args=accepted['browser_flags'])
    try:
        for original in accepted['pages']:
            source = Path(original['page']['path'])
            assert rec(source) == original['page']
            context = browser.new_context(offline=True, viewport={'width': 1440, 'height': 1000})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            def route(request_route):
                if request_route.request.url.startswith('file:'):
                    request_route.continue_()
                else:
                    attempts.append(request_route.request.url.split(':', 1)[0])
                    request_route.abort()
            context.route('**/*', route)
            page.goto(source.as_uri(), wait_until='load', timeout=600000)
            if source.name != 'index.html':
                page.wait_for_function('window.PAGE_READY===true||window.PAGE_ERROR!==undefined', timeout=600000)
                assert not page.evaluate('window.PAGE_ERROR||null')
            page.evaluate('document.fonts.ready')
            assert page.evaluate('document.fonts.check(\'16px "Noto Sans CJK SC"\', "全量进程时间线")')
            target = OUT / ('preview_zh_' + source.stem + '.png')
            page.screenshot(path=str(target), full_page=False)
            assert not errors and not attempts and rec(source) == original['page']
            results.append({'accepted_page': original['page'], 'readable_preview': rec(target),
                            'same_accepted_HTML_SHA256': True, 'page_errors': errors})
            context.close()
            print('READABLE_CHINESE_PREVIEW_COMPLETE', source.name, flush=True)
    finally:
        browser.close()
result = {'status': 'complete', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'purpose': 'supplementary readable Chinese previews; original formal acceptance retained',
          'font_installation': rec(OUT / 'FONT_INSTALLATION.json'), 'pages': results,
          'accepted_HTML_files_changed': False, 'network_attempts': attempts,
          'all_browser_processes_closed_before_result': True, 'code': rec(Path(__file__))}
(OUT / 'READABLE_PREVIEWS_COMPLETE.json').write_text(json.dumps(result, indent=2) + '\n')
print('ALL_FIVE_READABLE_CHINESE_PREVIEWS_COMPLETE', flush=True)
