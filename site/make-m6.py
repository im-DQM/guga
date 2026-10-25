#!/usr/bin/env python3
# 由 m.html 生成 m6.html（手机端 · 咕嘎六号）：主界面=对话，连接信息收进按钮/抽屉
import re, sys, pathlib

src = pathlib.Path('/home/ubuntu/stack/hub/m.html').read_text(encoding='utf-8')
o = src

def rep(old, new, why, count=1):
    global o
    n = o.count(old)
    if n != count:
        sys.exit('锚点不匹配（%s）：期望 %d 处，实际 %d 处\n--- %s' % (why, count, n, old[:120]))
    o = o.replace(old, new)
    print('✓', why)

# 1) 标题
rep('<title>咕嘎一号 · 手机版</title>', '<title>咕嘎六号 · 手机版</title>', '标题')

# 1b) 走「远程操作」分身：自己的会话、自己的记忆，跟管家分开
rep("const API='/api/hermes';",
    "const API='/api/hermes/p/remote';   // 六号 = 远程操作分身：自己的会话与记忆，看不到管家那边（主人 2026-10-13 要的）",
    'API 走远程分身')

# 2) 头部：标题 + 连接信息按钮
rep('''  <div class="title">
    <div class="tw"><span class="nm"><span class="dot" style="display:inline-block;margin-right:6px"></span><span id="agentName">咕嘎一号</span></span>
    <span class="sub" id="subline">管家 · 随时待命</span></div>
  </div>
''', '''  <div class="title">
    <div class="tw"><span class="nm"><span class="dot six" style="display:inline-block;margin-right:6px"></span><span id="agentName">咕嘎六号</span></span>
    <span class="sub" id="subline">正在看接入状态…</span></div>
  </div>
  <button class="ibtn" id="connBtn" aria-label="连接信息">
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/></svg>
  </button>
''', '头部标题与连接按钮')

# 3) 抽屉底部按钮
rep('''  <div class="dfoot">
    <button type="button" id="todoBtn">计划</button>
    <button type="button" id="sitesBtn">站点</button>
    <a href="/m6.html">六号</a>
    <a href="/group.html">咕嘎群</a>
  </div>
''', '''  <div class="dfoot">
    <button type="button" id="connBtn2">连接信息</button>
    <a href="https://join.dqmguga.site/join.html" target="_blank" rel="noopener">接入页</a>
    <a href="/group.html">咕嘎群</a>
    <a href="/m.html">管家</a>
  </div>
''', '抽屉底部')

# 4) 面板：站点/待办 → 连接信息
sites_sheet_start = o.index('<div class="sheet" id="sitesSheet"')
script_start = o.index('<script>\n(function(){')
old_sheets = o[sites_sheet_start:script_start]
if 'todoSheet' not in old_sheets or 'sitesSheet' not in old_sheets:
    sys.exit('面板区块识别失败')
new_sheet = '''<div class="sheet" id="connSheet" aria-label="连接信息">
  <div class="sh"><span class="tt">连接信息</span><span class="sm" id="connCount"></span>
    <button class="x" type="button" id="connClose" aria-label="关闭">✕</button></div>
  <div class="tlist" id="connList"><div class="tempty">读取中…</div></div>
</div>

'''
o = o[:sites_sheet_start] + new_sheet + o[script_start:]
print('✓ 面板换成连接信息')

# 5) JS：待办面板 + 站点面板 → 连接信息面板
todo_js_start = o.index('/* ── 待办面板（抽屉底部「待办」→ 今天要做什么')
voice_js_start = o.index('/* ── 语音输入')
new_js = r'''/* ── 连接信息（谁接进来了、给的什么权限、一条断开并撤销） ───── */
const connSheet=$('#connSheet'), connList=$('#connList'), connCount=$('#connCount');
const JOIN_BASE='https://join.dqmguga.site/join.html';
let guests=[], guest=null;          // guest = 当前用于对话的那台（取第一台在线的）
let connTimer=null;

function copyText(t,okMsg,failMsg){
  const ok=()=>say(okMsg||'已复制');
  const fb=()=>{
    try{
      const ta=document.createElement('textarea'); ta.value=t; ta.setAttribute('readonly','');
      ta.style.cssText='position:fixed;left:-9999px;top:0;opacity:0';
      document.body.appendChild(ta); ta.select(); ta.setSelectionRange(0,ta.value.length);
      const done=document.execCommand('copy'); ta.remove();
      done?ok():say(failMsg||'复制失败：长按手动选中吧');
    }catch(e){ say('复制失败：'+e.message); }
  };
  if(navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(t).then(ok).catch(fb);
  else fb();
}
function pickGuest(){
  const on=guests.filter(g=>g.connected);
  guest = on.length ? on[0] : null;
  return guest;
}
function syncHeader(){
  const g=pickGuest();
  const sub=$('#subline');
  if(g) sub.textContent='已接入：'+(g.name||'一台机器');
  else  sub.textContent='现在没有机器接进来';
}
function gcard(g){
  const c=document.createElement('div'); c.className='gcard';
  const hd=document.createElement('div'); hd.className='hd';
  const dot=document.createElement('span'); dot.className='gdot'+(g.connected?'':' off');
  if(!g.connected) dot.style.background='var(--faint)', dot.style.boxShadow='none';
  const nm=document.createElement('span'); nm.textContent=g.name||'（未命名）';
  hd.append(dot,nm);
  const gd=document.createElement('div'); gd.className='gd';
  gd.textContent=[ (g.os==='windows'?'Windows':(g.os||'未知系统')),
                   g.user?('用户 '+g.user):'',
                   (g.mode==='full'?'完整协助':'只读协助'),
                   '端口 '+g.port,
                   g.connected?'在线':'已断开' ].filter(Boolean).join(' · ');
  const tm=document.createElement('div'); tm.className='gd';
  tm.textContent=g.created?('接入于 '+new Date(g.created*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})+' · 已 '+Math.max(0,Math.floor((Date.now()/1000-g.created)/60))+' 分钟'):'';
  const bar=document.createElement('div'); bar.className='gb';
  const chat=document.createElement('button'); chat.type='button'; chat.className='primary';
  chat.textContent='跟它对话'; chat.onclick=()=>{ closeSites(); closeDrawer();
    connSheet.classList.remove('open');
    (async()=>{ if(!currentId) await newSession(); })().then(()=>{
      say('往下说就行 —— 我在这台机器上干活。'); if(input) input.focus();
    });
  };
  const rv=document.createElement('button'); rv.type='button'; rv.className='danger';
  rv.textContent='断开并撤销';
  rv.onclick=async ()=>{
    if(!confirm('断开「'+(g.name||'')+'」？钥匙会作废，那边十几秒内自己把隧道拆掉。')) return;
    rv.disabled=true; rv.textContent='正在断开…';
    try{
      const r=await fetch('/api/join/revoke',{method:'POST',headers:{'content-type':'application/json'},
                                              body:JSON.stringify({id:g.id})});
      if(!r.ok) throw new Error('HTTP '+r.status);
      say('已作废 —— 十几秒内那边会自己拆干净。');
      await loadGuests(); renderConn();
    }catch(e){ rv.disabled=false; rv.textContent='断开并撤销'; say('断开失败：'+e.message); }
  };
  bar.append(chat,rv);
  c.append(hd,gd); if(tm.textContent) c.append(tm); c.append(bar);
  return c;
}
function renderConn(){
  connCount.textContent = guests.length ? (guests.length+' 台') : '';
  connList.innerHTML='';
  if(!guests.length){
    const e=document.createElement('div'); e.className='tempty';
    e.innerHTML='现在没有机器接进来<br><br>把接入页发给对方：他打开 → 输连接密码 → 点「同意」 → 在他自己电脑上跑一条命令，就接进来了。';
    const cp=document.createElement('button'); cp.type='button'; cp.className='newbtn';
    cp.style.cssText='margin-top:14px'; cp.textContent='复制接入页链接';
    cp.onclick=()=>copyText(JOIN_BASE,'已复制接入页链接：'+JOIN_BASE);
    e.appendChild(document.createElement('div')).appendChild(cp);
    connList.appendChild(e);
    return;
  }
  guests.forEach(g=>connList.appendChild(gcard(g)));
  const hint=document.createElement('div'); hint.className='tempty';
  hint.style.padding='14px 4px 4px';
  hint.textContent='断线后这台机器就从服务器上消失了（它没有记忆文件，这段对话也只在这次连接里）。';
  connList.appendChild(hint);
}
async function loadGuests(){
  try{
    const r=await fetch('/api/join/guests',{cache:'no-store'});
    if(!r.ok) throw new Error('HTTP '+r.status);
    guests=((await r.json()).guests||[]);
  }catch(e){ guests=[]; }
  syncHeader();
  if(connSheet.classList.contains('open')) renderConn();
  stateEmpty();
}
function openSites(){ closeDrawer(); connSheet.classList.add('open'); renderConn(); loadGuests(); }
function closeSites(){ connSheet.classList.remove('open'); }
$('#connBtn').addEventListener('click',openSites);
$('#connBtn2').addEventListener('click',openSites);
$('#connClose').addEventListener('click',closeSites);

'''
o = o[:todo_js_start] + new_js + o[voice_js_start:]
print('✓ JS 面板换成连接信息')

# 6) 样式补充（六号色点 + 卡片）
rep('''.enddot{display:block;width:6px;height:6px;border-radius:50%;background:#1E4A9E;margin-top:9px}''',
'''.enddot{display:block;width:6px;height:6px;border-radius:50%;background:#1E4A9E;margin-top:9px}
.title .dot.six{background:linear-gradient(135deg,#8FE3FF,#5AC8FA);box-shadow:0 0 12px #5AC8FA66}
.gcard{border:1px solid var(--border);border-radius:var(--r-md);background:var(--surface);padding:12px;margin-bottom:10px;display:flex;flex-direction:column;gap:7px}
.gcard .hd{display:flex;align-items:center;gap:9px;font-size:15px;font-weight:600}
.gcard .gd{font-size:12.5px;color:var(--muted);line-height:1.7}
.gcard .gb{display:flex;gap:8px;flex-wrap:wrap;margin-top:3px}
.gcard button{border:1px solid var(--border);background:transparent;color:var(--fg);border-radius:var(--r-sm);padding:8px 13px;font-size:13px;font-family:inherit;cursor:pointer}
.gcard button.primary{border-color:var(--accent);color:var(--accent)}
.gcard button.danger{border-color:#FF453A66;color:#FF8E86}
.gdot{width:9px;height:9px;border-radius:50%;background:var(--ok);box-shadow:0 0 10px #30D15866;flex:0 0 auto}''', '样式补充')

# 7) 空态文案
rep("""  e.innerHTML='<h3>咕嘎一号随时待命</h3><p>主人的待办、提醒、服务器上的活儿，<br>直接说就行。<br><br>左下角能翻以前的对话，<br>右上角「＋」开新的。</p>';""",
"""  e.innerHTML='<h3>咕嘎六号随时待命</h3><p>接进来的机器，在这儿说人话就能操作它。<br>要动那台机器时，会弹「批准 / 拒绝」让你点头。<br><br>左上角翻以前的对话，右上角「＋」开新的；<br>顶栏那个链接图标是「连接信息」。</p>';""".replace("'" , "'"), '空态文案')

# 8) startRun 带上六号的身份提示
rep('''async function startRun(text){
  const r=await fetch(API+'/v1/runs',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({input:text,session_id:currentId})});''',
'''async function startRun(text){
  const body={input:text, session_id:currentId};
  const ins=guestInstructions();          // 临时系统提示：不落进会话历史
  if(ins) body.instructions=ins;
  const r=await fetch(API+'/v1/runs',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify(body)});''', 'startRun 带身份提示')

# 9) guestInstructions + stateEmpty（放在 addUser 之前）
rep('''function addUser(text, files){ const w=document.createElement('div'); w.className='msg user';''',
'''/* ── 六号的身份提示 + 空态刷新（连接一变就跟着变） ─────────── */
function guestInstructions(){
  const g=pickGuest(); if(!g) return null;
  return [
    '你就是「咕嘎六号」—— 咕嘎一号的**远程操作**分身，只管替主人在**临时接进来的那台机器**上干活。',
    '**你不记得主人的生活**（待办、饮食、作息、朋友那些都在管家那边）—— 被问到就直说：「那些在我管家那边，这边看不到。」',
    '现在接进来的是：'+(g.name||'一台机器')+'（系统 '+g.os+'，用户名 '+(g.user||'未知')+'，端口 '+g.port
      +'，权限：'+(g.mode==='full'?'**完整协助**':'**只读协助**（写/危险命令会被服务端 403 拒掉）')+'）。',
    '你**有自己的记忆文件**：`~/.hermes/guga6/MEMORY.md`（你自己那一份，和管家的记忆分开）。动手前先读它；学到跟接入、这类机器有关的长期事实（常客、它的环境、路径、踩过的坑）就**按机器名分节**写回去。',
    '这段对话**只属于这一次连接**：对方一撤销、连接一断它就没了 —— 要紧的当场说完，值得留的写进上面那份记忆。',
    '要在这台机器上执行命令，**不要用 ssh 别名**（它不在主机清单里），走服务器的 join 服务：',
    '  执行： curl -s -X POST http://127.0.0.1:8793/exec -H "X-Guga-Join-Admin: Bearer $(sudo cat /etc/guga/join_admin_secret)" -H "content-type: application/json" -d \\'{"id":"'+g.id+'","cmd":"<命令>"}\\'',
    '  它会回 need_confirm 和一个 id；再放行： curl -s -X POST http://127.0.0.1:8793/approve -H "X-Guga-Join-Admin: Bearer $(sudo cat /etc/guga/join_admin_secret)" -H "content-type: application/json" -d \\'{"id":"<id>","decision":"yes"}\\'',
    '只读协助下要动手就先请对方改成「完整协助」。',
  ].join('\\n');
}
function stateEmpty(){
  const e=main.querySelector('.empty');
  if(!e) return;
  const g=pickGuest();
  e.innerHTML = g
    ? '<h3>'+(g.name||'咕嘎六号')+' 在线</h3><p>直接说想让它在<b>那台机器</b>上做什么，<br>要动手时我会先弹「批准 / 拒绝」。</p>'
    : '<h3>咕嘎六号随时待命</h3><p>现在没有机器接进来。<br>点顶栏的链接图标 → 复制接入页链接发给对方，<br>他打开点「同意」并跑一条命令就接进来了。</p>';
}
function addUser(text, files){ const w=document.createElement('div'); w.className='msg user';''', '身份提示与空态')

# 10) 启动流程：先拉接入状态，再把会话和这台机器绑上
rep('''(async function start(){
  grow(); syncIdle();
  await refreshSessions();
  if(sessions.length){ await selectSession(sessions[0].id); }
  else await newSession();
  refreshInbox();
})();''',
'''(async function start(){
  grow(); syncIdle();
  await loadGuests();
  await refreshSessions();
  // 优先接上这段连接自己的对话（桌面「远程连接」里挑的那一段），没有就挑最近一段
  const g=pickGuest();
  const want = (g && g.session_id && sessions.some(s=>s.id===g.session_id)) ? g.session_id
             : (sessions.length ? sessions[0].id : null);
  if(want) await selectSession(want); else await newSession();
  refreshInbox();
  connTimer=setInterval(()=>{ if(!document.hidden){ loadGuests(); refreshSessions(); } },20000);
})();''', '启动流程')

# 11) 会话与机器绑定：每段对话都记在这台 guest 名下
rep('''async function selectSession(id){
  if(id===currentId) return;
  currentId=id; renderSessions(); loadMessages(id);
}''',
'''async function bindGuest(){
  const g=pickGuest();
  if(!g || !currentId) return;
  try{ await fetch('/api/join/session',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({id:g.id, session_id:currentId})}); }catch(e){}
}
async function selectSession(id){
  if(id===currentId) return;
  currentId=id; renderSessions(); loadMessages(id); bindGuest();
}''', '会话绑定机器')

rep('''    currentId=s.id; renderSessions(); showEmpty();
    agentName.textContent='咕嘎一号'; subline.textContent='新对话';''',
'''    currentId=s.id; renderSessions(); showEmpty();
    agentName.textContent='咕嘎六号';
    const gg=pickGuest();                    // 有机器在，就给这段对话挂个认得出的名字
    if(gg){ try{ await fetch(API+'/api/sessions/'+encodeURIComponent(s.id),{method:'PATCH',
      headers:{'content-type':'application/json'},
      body:JSON.stringify({title:'六号 · '+(gg.name||'接入的机器')+' · '+new Date().toTimeString().slice(0,5)})}); }catch(e){} }
    bindGuest();''', '新对话后绑定')

pathlib.Path('/home/ubuntu/stack/hub/m6.html').write_text(o, encoding='utf-8')
print('\n写出 /home/ubuntu/stack/hub/m6.html：%d 字节' % len(o.encode('utf-8')))
