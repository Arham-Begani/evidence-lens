"""Test finite UI motion, user/OS preferences and the actual redesigned local page."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
from check_desk_browser import CONTRAST, EDGE


def run(url, output):
    if urlparse(url).hostname not in ('localhost','127.0.0.1'):
        raise ValueError('Only local previews are permitted')
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    report={'url':url,'errors':[],'external_requests':[],'layouts':[],
            'scope':'Interface engineering checks, not research results or a full accessibility certification.'}
    def settle(page):
        page.evaluate('() => Promise.allSettled(document.getAnimations().map(a=>a.finished))')
    def active(page):
        return page.evaluate('document.getAnimations().filter(a=>a.playState==="running").length')
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=EDGE,headless=True)
            context=browser.new_context(viewport={'width':1440,'height':900},reduced_motion='no-preference')
            page=context.new_page()
            page.on('pageerror',lambda e:report['errors'].append(str(e)))
            page.on('request',lambda r:report['external_requests'].append(r.url) if urlparse(r.url).hostname not in ('localhost','127.0.0.1') else None)
            page.goto(url)
            expect(page.locator('html')).to_have_attribute('data-motion','on')
            expect(page.locator('#motion-toggle')).to_have_attribute('aria-pressed','true')
            timings=page.evaluate('document.getAnimations().map(a=>({duration:a.effect.getTiming().duration,iterations:a.effect.getTiming().iterations}))')
            assert timings and all(t['iterations']==1 and t['duration']<=800 for t in timings),timings
            settle(page);assert active(page)==0
            page.locator('#trace-replay').click()
            page.wait_for_timeout(90)  # Intentional sampling of an animation's intermediate frame.
            offset=page.locator('.wire-active path').first.evaluate('(e)=>parseFloat(getComputedStyle(e).strokeDashoffset)')
            assert 0<offset<1,offset
            first=page.screenshot(path=str(out/'trace-in-progress.png'))
            settle(page)
            last=page.screenshot(path=str(out/'trace-complete.png'))
            assert first!=last
            report['trace']={'finite_initial_animations':len(timings),'sampled_intermediate_offset':offset,'distinct_rendered_frames':True,'settled_running_animations':active(page)}
            page.locator('#trace-replay').click();assert active(page)>0
            page.locator('#motion-toggle').click()
            expect(page.locator('html')).to_have_attribute('data-motion','off')
            assert active(page)==0
            expect(page.locator('#trace-replay')).to_be_disabled()
            page.locator('[data-specimen="p2"]').click()
            assert 'Remote' in page.locator('#specimen-summary').text_content()
            assert active(page)==0
            page.locator('#motion-toggle').click()
            page.locator('#method').select_option('instruction')
            assert active(page)>0
            settle(page)
            citation=page.locator('#answer .citation').last;citation.click()
            assert page.locator('#passage-dialog').evaluate('(e)=>getComputedStyle(e).animationName')=='reader-enter'
            page.keyboard.press('Escape');expect(citation).to_be_focused()
            page.locator('#trace-replay').click()
            page.emulate_media(reduced_motion='reduce')
            expect(page.locator('html')).to_have_attribute('data-motion','off')
            expect(page.locator('#motion-toggle')).to_be_disabled()
            assert active(page)==0
            page.emulate_media(reduced_motion='no-preference')
            expect(page.locator('html')).to_have_attribute('data-motion','on')
            page.locator('#motion-toggle').click()
            page.emulate_media(reduced_motion='reduce');page.emulate_media(reduced_motion='no-preference')
            expect(page.locator('html')).to_have_attribute('data-motion','off')
            page.locator('#motion-toggle').focus();page.keyboard.press('Space')
            expect(page.locator('html')).to_have_attribute('data-motion','on')
            report['motion_controls']={'manual_cancel':True,'off_during_interaction':True,'os_reduce_cancel':True,'manual_choice_survives_os_changes':True,'keyboard_toggle':True,'escape_during_reader_animation':True}
            context.close()
            for width in (1440,1024,768,390,320):
                context=browser.new_context(viewport={'width':width,'height':900},reduced_motion='no-preference')
                page=context.new_page();page.on('pageerror',lambda e:report['errors'].append(str(e)))
                page.goto(url);settle(page)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(out/f'hero-{width}.png'))
                page.screenshot(path=str(out/f'full-{width}.png'),full_page=True)
                contrast=page.evaluate(CONTRAST);assert not contrast['failures'],contrast
                page.locator('.primary-action').click()
                # Disable smooth scrolling before the position and screenshot checks.
                page.locator('#workspace').evaluate('(e)=>e.scrollIntoView({block:"start",behavior:"instant"})')
                page.screenshot(path=str(out/f'desk-{width}.png'))
                first_claim_y=page.locator('#answer .claim-title p').first.bounding_box()['y']
                page.locator('#answer .citation').last.click();settle(page)
                page.screenshot(path=str(out/f'reader-{width}.png'))
                assert not page.evaluate(CONTRAST)['failures']
                expect(page.locator('#close-dialog')).to_be_focused()
                page.keyboard.press('Shift+Tab');expect(page.locator('#view-in-packet')).to_be_focused()
                page.keyboard.press('Tab');expect(page.locator('#close-dialog')).to_be_focused()
                page.locator('#view-in-packet').click()
                page.evaluate('() => new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                expect(page.locator('[id="passage-d2:p3"]')).to_be_focused()
                report['layouts'].append({'width':width,'overflow':False,'contrast':contrast,'first_claim_y':first_claim_y,'reader_focus':True})
                context.close()
            context=browser.new_context(viewport={'width':320,'height':640},reduced_motion='reduce')
            page=context.new_page();page.goto(url);page.locator('#answer .citation').last.click()
            close=page.locator('#close-dialog').bounding_box();action=page.locator('#view-in-packet').bounding_box()
            assert close['y']>=0 and action['y']+action['height']<=640
            assert page.locator('.dialog-content').evaluate('(e)=>e.scrollHeight>e.clientHeight')
            page.screenshot(path=str(out/'reader-short-phone.png'))
            report['short_phone']={'width':320,'height':640,'controls_visible':True,'content_scrolls':True}
            context.close();browser.close()
        assert not report['errors'] and not report['external_requests']
        report['status']='passed'
    except Exception as error:
        report['status']='failed';report['failure']=repr(error);raise
    finally:
        (out/'checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'finite_motion':report['trace'],'layouts':len(report['layouts']),'output':str(out)},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url');parser.add_argument('output');args=parser.parse_args()
    run(args.url,args.output)
