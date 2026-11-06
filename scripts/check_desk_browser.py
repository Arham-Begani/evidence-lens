"""Bounded local Edge checks. No external navigation, model calls or browser installs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse, urljoin
from urllib.request import build_opener, ProxyHandler
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
CONTRAST = r'''() => {
 const rgba=s=>{const v=s.match(/[\d.]+/g).map(Number);return [v[0],v[1],v[2],v.length>3?v[3]:1]};
 const blend=(a,b)=>a.slice(0,3).map((v,i)=>v*a[3]+b[i]*(1-a[3]));
 const luminance=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
 const ratio=(a,b)=>{const x=luminance(a),y=luminance(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
 const checked=[],failures=[];
 for(const el of document.querySelectorAll('body *')){
   if(!el.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||el.closest('.sr-only,script,style,[disabled]')||!Array.from(el.childNodes).some(n=>n.nodeType===3&&n.textContent.trim()))continue;
   let ancestors=[],node=el;while(node){ancestors.unshift(node);node=node.parentElement;}
   if(ancestors.some(n=>Number(getComputedStyle(n).opacity)<1))continue;
   let bg=[255,255,255];for(const n of ancestors)bg=blend(rgba(getComputedStyle(n).backgroundColor),bg);
   const style=getComputedStyle(el),fg=blend(rgba(style.color),bg),size=parseFloat(style.fontSize),weight=parseInt(style.fontWeight)||400;
   const minimum=size>=24||(size>=18.66&&weight>=700)?3:4.5,actual=ratio(fg,bg);
   const item={element:el.tagName.toLowerCase()+(el.id?'#'+el.id:''),text:el.textContent.trim().slice(0,90),ratio:Math.round(actual*100)/100,minimum,size};
   checked.push(item);if(actual+.01<minimum)failures.push(item);
 }
 return {checked:checked.length,failures,minimumObserved:Math.min(...checked.map(x=>x.ratio))};
}'''


def run(url, output):
    if urlparse(url).hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('Only the existing local demo is allowed')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'url': url, 'browser': 'installed Microsoft Edge, headless', 'states': [],
              'citation_checks': 0, 'layouts': [], 'failures': [], 'new_inference': 0,
              'external_requests': [], 'page_errors': [], 'accessibility_scope':
              'Automated contrast, names, reflow and keyboard checks; not full WCAG certification.'}
    opener = build_opener(ProxyHandler({}))
    html = opener.open(url, timeout=10).read().decode('utf-8')
    report['html_sha256'] = hashlib.sha256(html.encode('utf-8')).hexdigest()
    payload = re.search(r'<script id="study-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    data = json.loads(payload)
    records = data['outcomes']
    def exact_answer(page, prefix, record):
        assert page.locator(prefix+' .claim-title p').all_text_contents() == [c['text'] for c in record['response']['claims']]
        assert page.locator(prefix+' .relationship').all_text_contents() == [c['reporting_relationship'] for c in record['response']['claims']]
        assert page.locator(prefix+' .limitations p').text_content() == record['response']['limitations']
    def selected(page, record):
        page.locator('#method').select_option(record['method'])
        page.locator('[data-condition="'+record['condition']+'"]').click()
        exact_answer(page, '#answer', record)
    def no_overflow(page):
        return page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=EDGE, headless=True)
            for width in (1440, 390):
                context = browser.new_context(viewport={'width':width, 'height':1000}, reduced_motion='reduce')
                page = context.new_page()
                page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
                page.on('request', lambda request: report['external_requests'].append(request.url) if urlparse(request.url).hostname not in ('127.0.0.1','localhost') else None)
                page.goto(url)
                expect(page.locator('#interactive-desk')).to_be_visible()
                for record in records:
                    selected(page, record)
                    assert page.locator('#sources .passage p').all_text_contents() == [passage['text'] for doc in record['packet']['documents'] for passage in doc['passages']]
                    lookup = {doc['id']+':'+v['id']:v['text'] for doc in record['packet']['documents'] for v in doc['passages']}
                    assert record['relative_directory'] in page.locator('#raw-answer').get_attribute('href')
                    for citation in page.locator('#answer .citation').all():
                        citation_id = citation.text_content()
                        citation.click()
                        expect(page.locator('#passage-dialog')).to_be_visible()
                        assert page.locator('#dialog-passage').text_content() == lookup[citation_id]
                        expect(page.locator('#close-dialog')).to_be_focused()
                        page.keyboard.press('Escape')
                        expect(page.locator('#passage-dialog')).not_to_be_visible()
                        expect(citation).to_be_focused()
                        report['citation_checks'] += 1
                    assert no_overflow(page)
                    report['states'].append({'width':width,'method':record['method'],'condition':record['condition'],'exact_text':True})
                ledger = next(r for r in records if r['method']=='ledger' and r['condition']=='mixed')
                selected(page, ledger)
                citation = page.locator('#answer .citation').last
                citation_id = citation.text_content()
                citation.click()
                for _ in range(14):
                    page.keyboard.press('Tab')
                    assert page.evaluate('document.activeElement.closest("dialog")!==null')
                page.locator('#previous-passage').click()
                assert page.locator('#citation-position').text_content() == '1 / 2'
                assert page.evaluate('document.activeElement.closest("dialog")!==null')
                page.locator('#next-passage').click()
                assert page.locator('#dialog-title').text_content() == citation_id
                page.locator('#view-in-packet').click()
                page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
                target = page.locator('[id="passage-'+citation_id+'"]')
                expect(target).to_be_focused()
                target.locator('.return-citation').click()
                expect(citation).to_be_focused()
                page.locator('#compare').check()
                exact_answer(page,'#comparison-answer',next(r for r in records if r['method']=='ordinary' and r['condition']=='mixed'))
                comparison_citation=page.locator('#comparison-answer .citation').last
                comparison_citation.click()
                expect(page.locator('#dialog-title')).to_have_text(comparison_citation.text_content())
                page.keyboard.press('Escape');expect(comparison_citation).to_be_focused()
                page.locator('#method').select_option('ordinary')
                expect(page.locator('#compare')).to_be_disabled()
                expect(page.locator('#comparison')).not_to_be_visible()
                assert 'compare=1' not in page.url
                page.locator('#method').select_option('document')
                page.locator('[data-condition="base"]').click()
                page.locator('[data-condition="repeat"]').click()
                page.go_back()
                assert 'condition=base' in page.url
                expect(page.locator('[data-condition="base"]')).to_have_attribute('aria-pressed','true')
                page.go_forward()
                page.reload()
                expect(page.locator('[data-condition="repeat"]')).to_have_attribute('aria-pressed','true')
                expect(page.locator('#method')).to_have_value('document')
                page.goto(url+'?method=__proto__&condition=constructor&compare=garbage')
                expect(page.locator('#method')).to_have_value('ledger')
                expect(page.locator('[data-condition="mixed"]')).to_have_attribute('aria-pressed','true')
                for passage_id in ('p2','p3'):
                    page.locator('[data-specimen="'+passage_id+'"]').click()
                    assert page.locator('#specimen-text').text_content() == next(v['text'] for d in ledger['packet']['documents'] if d['id']=='d2' for v in d['passages'] if v['id']==passage_id)
                context.close()
            for width in (1440,1024,768,390,320):
                context = browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce')
                page = context.new_page();page.goto(url)
                expect(page.locator('#interactive-desk')).to_be_visible()
                assert no_overflow(page)
                assert page.evaluate('getComputedStyle(document.documentElement).scrollBehavior') == 'auto'
                assert page.locator('.primary-action').evaluate('(e)=>getComputedStyle(e).transitionDuration') == '0s'
                page.keyboard.press('Tab');expect(page.locator('.skip')).to_be_focused()
                assert page.locator('.skip').evaluate('(e)=>getComputedStyle(e).outlineWidth') == '3px'
                page.keyboard.press('Enter')
                assert page.url.endswith('#workspace')
                page.locator('#method').focus()
                assert page.locator('#method').evaluate('(e)=>getComputedStyle(e).outlineWidth') == '3px'
                # Return to a clean entry state before screenshots.
                page.goto(url)
                page.screenshot(path=str(output/f'full-{width}.png'),full_page=True)
                page.screenshot(path=str(output/f'hero-{width}.png'))
                page.locator('#workspace').evaluate('(e)=>e.scrollIntoView({block:"start",behavior:"instant"})')
                page.screenshot(path=str(output/f'desk-{width}.png'))
                contrast = page.evaluate(CONTRAST)
                assert not contrast['failures'], contrast['failures']
                ax = context.new_cdp_session(page).send('Accessibility.getFullAXTree')
                unnamed = [node['role']['value'] for node in ax['nodes'] if not node.get('ignored') and node.get('role',{}).get('value') in ('button','link','combobox','checkbox') and not node.get('name',{}).get('value')]
                assert not unnamed, unnamed
                page.locator('#answer .citation').last.click()
                modal_contrast = page.evaluate(CONTRAST)
                assert not modal_contrast['failures'], modal_contrast['failures']
                page.screenshot(path=str(output/f'reader-{width}.png'))
                assert no_overflow(page)
                report['layouts'].append({'width':width,'overflow':False,'contrast':contrast,'modal_contrast':modal_contrast,'unnamed_controls':unnamed,'reduced_motion':True,'visible_focus':True})
                context.close()
            # Browser-local fault injection changes no artifact and requests no new inference.
            faults = {}
            for name in ('malformed','missing-citation','empty-answer'):
                altered = json.loads(payload)
                if name=='malformed': altered['outcomes']=[]
                record=next((r for r in altered['outcomes'] if r['method']=='ledger' and r['condition']=='mixed'),None)
                if name=='missing-citation': record['response']['claims'][0]['citations']=['d9:p9']
                if name=='empty-answer': record['response']['claims']=[]
                substituted = html.replace(payload,json.dumps(altered,ensure_ascii=True))
                context=browser.new_context(viewport={'width':390,'height':1000})
                context.route(url,lambda route:route.fulfill(status=200,content_type='text/html',body=substituted))
                page=context.new_page();page.goto(url)
                if name=='malformed':
                    expect(page.locator('#data-error')).to_be_visible();expect(page.locator('#interactive-desk')).not_to_be_visible()
                elif name=='missing-citation':
                    page.locator('#answer .citation').first.click();expect(page.locator('#action-message')).to_be_visible()
                    assert 'd9:p9' in page.locator('#action-message').text_content()
                else: expect(page.locator('.empty-answer')).to_be_visible()
                page.screenshot(path=str(output/(name+'.png')),full_page=True)
                faults[name]='passed';context.close()
            context=browser.new_context(java_script_enabled=False)
            page=context.new_page();page.goto(url)
            expect(page.locator('noscript a')).to_be_visible()
            faults['javascript-disabled']='static report link visible';context.close()
            report['failure_states']=faults
            # Links are verified locally; external publication links are not followed.
            context=browser.new_context();page=context.new_page();page.goto(url)
            links=page.locator('a[href]').evaluate_all('(nodes)=>nodes.map(n=>n.href)')
            local=sorted({u.split('#')[0] for u in links if urlparse(u).hostname=='127.0.0.1'})
            report['local_links']={u:opener.open(u,timeout=10).status for u in local}
            assert all(status==200 for status in report['local_links'].values())
            context.close();browser.close()
        assert not report['page_errors'],report['page_errors']
        assert not report['external_requests'],report['external_requests']
        report['status']='passed'
    except Exception as error:
        report['status']='failed';report['failures'].append(repr(error));raise
    finally:
        (output/'checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'states':len(report['states']),'citations':report['citation_checks'],'layouts':len(report['layouts']),'output':str(output)},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url');parser.add_argument('output')
    args=parser.parse_args();run(args.url,args.output)
