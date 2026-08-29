(() => {
  const PROGRESS_KEY = 'progress-v1';
  const SETTINGS_KEY = 'lingodeck-settings-v1';
  const FALLBACK_CSV = './sample-data/words.csv';
  const MASTERY = {
    weak: { label: '苦手', color: '#d8685a', rank: 0 },
    fuzzy: { label: 'うろ覚え', color: '#d9a52d', rank: 1 },
    almost: { label: 'ほぼ覚えた', color: '#6687bd', rank: 2 },
    mastered: { label: '覚えた', color: '#3f9c70', rank: 3 },
  };
  const DAY = 86400000;

  const state = {
    route: 'home', words: [], source: 'loading', progress: {},
    settings: Object.assign({
      sheetCsvUrl: window.LINGODECK_CONFIG?.sheetCsvUrl || '', dailyGoal: 20, sessionSize: 20,
      autoSpeak: true, includeNew: true,
    }, loadJson(SETTINGS_KEY, {})),
    session: null,
  };

  function loadJson(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
  function saveProgress() { window.LingoDeckDB.set(PROGRESS_KEY, state.progress).catch(()=>{}); }
  function saveSettings() { localStorage.setItem(SETTINGS_KEY, JSON.stringify(state.settings)); }
  const now = () => Date.now();
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const shuffle = arr => arr.map(v => [Math.random(), v]).sort((a,b)=>a[0]-b[0]).map(x=>x[1]);

  function parseCSV(text) {
    const rows = []; let row = [], field = '', q = false;
    for (let i=0;i<text.length;i++) {
      const c=text[i], n=text[i+1];
      if (q) { if (c==='"' && n==='"') { field+='"'; i++; } else if(c==='"') q=false; else field+=c; }
      else if(c==='"') q=true; else if(c===','){row.push(field);field='';} else if(c==='\n'){row.push(field);rows.push(row);row=[];field='';} else if(c!=='\r') field+=c;
    }
    if(field || row.length){row.push(field);rows.push(row)}
    if(!rows.length) return [];
    const headers=rows.shift().map(h=>h.trim().toLowerCase());
    return rows.filter(r=>r.some(Boolean)).map((r,i)=>Object.fromEntries(headers.map((h,j)=>[h,(r[j]??'').trim()]))).map((x,i)=>({
      id: x.id || `row-${i+1}`, word:x.word, meaning:x.meaning, pronunciation:x.pronunciation || '', example:x.example || '',
      example_ja:x.example_ja || '', part_of_speech:x.part_of_speech || '', level:x.level || '', tags:x.tags || '',
      enabled: !['0','false','no','off'].includes((x.enabled||'true').toLowerCase()),
    })).filter(x=>x.enabled && x.word && x.meaning);
  }

  async function loadWords(force=false) {
    const url = state.settings.sheetCsvUrl.trim() || FALLBACK_CSV;
    const fetchUrl = force && !url.startsWith('./') ? `${url}${url.includes('?')?'&':'?'}_=${Date.now()}` : url;
    try {
      const res = await fetch(fetchUrl, { cache: force ? 'no-store' : 'default' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const csv = await res.text(); const words = parseCSV(csv);
      if (!words.length) throw new Error('No rows');
      state.words=words; state.source = state.settings.sheetCsvUrl.trim() ? 'Google Sheets' : '同梱サンプル';
    } catch (err) {
      if (url !== FALLBACK_CSV) {
        const res=await fetch(FALLBACK_CSV); state.words=parseCSV(await res.text()); state.source='同梱サンプル（Sheets取得失敗）';
      } else { state.words=[]; state.source='読み込み失敗'; }
    }
    ensureProgress(); render();
  }

  function ensureProgress() {
    for (const w of state.words) if (!state.progress[w.id]) state.progress[w.id] = {
      seen:0, correct:0, wrong:0, streak:0, stability:0, difficulty:5, dueAt:0, lastReviewedAt:0,
      lastResult:null, avgResponseMs:0, mastery:'weak', history:[], cardKnown:null,
    };
    saveProgress();
  }

  function masteryFrom(p) {
    if (!p.seen || p.lastResult === 'wrong' || p.stability < 1) return 'weak';
    if (p.stability < 4) return 'fuzzy';
    if (p.stability < 14) return 'almost';
    return (p.correct >= p.wrong && p.streak >= 2) ? 'mastered' : 'almost';
  }

  function updateMemory(wordId, correct, responseMs) {
    const p=state.progress[wordId], oldS=p.stability||0;
    p.seen++; correct ? p.correct++ : p.wrong++;
    p.streak = correct ? p.streak+1 : 0; p.lastResult=correct?'correct':'wrong'; p.lastReviewedAt=now();
    p.avgResponseMs = p.avgResponseMs ? Math.round(p.avgResponseMs*.75 + responseMs*.25) : responseMs;
    if(!correct){p.stability=Math.max(.15, oldS*.25);p.difficulty=clamp(p.difficulty+.7,1,10)}
    else {
      const speed = responseMs < 1500 ? 3.0 : responseMs < 4000 ? 2.2 : 1.45;
      p.stability = oldS < .5 ? 1 : clamp(oldS * speed * (1.08 - p.difficulty*.018), .5, 3650);
      p.difficulty=clamp(p.difficulty-(responseMs<4000?.18:.05),1,10);
    }
    p.dueAt = now() + p.stability*DAY; p.mastery=masteryFrom(p);
    p.history.push({t:now(),correct,ms:responseMs}); if(p.history.length>120)p.history=p.history.slice(-120);
    saveProgress();
  }

  function recallProbability(p) {
    if(!p.lastReviewedAt || !p.stability) return 0;
    const days=(now()-p.lastReviewedAt)/DAY;
    return Math.pow(.9, days/p.stability);
  }

  function selectSession(size, reviewOnly=false) {
    const t=now();
    const scored=state.words.map(w=>{const p=state.progress[w.id]; const overdue=Math.max(0,(t-(p.dueAt||0))/DAY); const newWord=!p.seen;
      const score=(newWord ? 30 : 0) + (p.dueAt<=t ? 100 : 0) + (3-MASTERY[p.mastery||'weak'].rank)*18 + overdue*4 + (1-recallProbability(p))*25;
      return {w,p,score,newWord};
    }).filter(x=>!reviewOnly || !x.newWord).filter(x=>state.settings.includeNew || !x.newWord || reviewOnly).sort((a,b)=>b.score-a.score);
    let chosen=scored.slice(0,size).map(x=>x.w);
    if(chosen.length<size && !reviewOnly) chosen = [...chosen, ...scored.slice(chosen.length,size).map(x=>x.w)];
    return chosen;
  }

  function allHistory(days=7) {
    const since=now()-days*DAY; const out=[];
    Object.values(state.progress).forEach(p=>(p.history||[]).forEach(h=>{if(h.t>=since)out.push(h)})); return out;
  }
  function dayBuckets(days=7) {
    const buckets=[]; const d=new Date(); d.setHours(0,0,0,0);
    for(let i=days-1;i>=0;i--){const s=d.getTime()-i*DAY,e=s+DAY;let c=0,ok=0;Object.values(state.progress).forEach(p=>(p.history||[]).forEach(h=>{if(h.t>=s&&h.t<e){c++;if(h.correct)ok++}}));buckets.push({s,c,ok,label:new Date(s).toLocaleDateString('ja-JP',{weekday:'short'})})}return buckets;
  }
  function todayCount(){const d=new Date();d.setHours(0,0,0,0);return allHistory(1.5).filter(h=>h.t>=d.getTime()).length}
  function streakDays(){const b=dayBuckets(60);let streak=0;for(let i=b.length-1;i>=0;i--){if(b[i].c>0)streak++;else if(i===b.length-1)continue;else break}return streak}

  function route(to){state.route=to;document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.route===to));render()}
  function clone(id){return document.getElementById(id).content.cloneNode(true)}
  function render(){const app=document.getElementById('app');app.innerHTML='';if(state.route==='home')renderHome(app);if(state.route==='learn')renderLearn(app);if(state.route==='words')renderWords(app);if(state.route==='stats')renderStats(app);if(state.route==='settings')renderSettings(app)}

  function renderHome(app){app.append(clone('homeTemplate'));
    const counts={weak:0,fuzzy:0,almost:0,mastered:0};state.words.forEach(w=>counts[state.progress[w.id]?.mastery||'weak']++);
    const due=state.words.filter(w=>(state.progress[w.id]?.dueAt||0)<=now()).length;
    document.getElementById('dataSourceLabel').textContent=`${state.source} · ${state.words.length}語`;
    document.getElementById('streakCount').textContent=streakDays();document.getElementById('dueText').textContent=`${due} words due`;document.getElementById('todayGoal').textContent=state.settings.dailyGoal;
    const tc=todayCount();document.getElementById('dailyProgress').style.width=`${clamp(tc/state.settings.dailyGoal*100,0,100)}%`;document.getElementById('wordCountLabel').textContent=`${state.words.length}語`;
    const mg=document.getElementById('masteryGrid');Object.entries(MASTERY).forEach(([k,m])=>mg.insertAdjacentHTML('beforeend',`<div class="mastery-card"><span class="dot" style="background:${m.color}"></span><small>${m.label}</small><b>${counts[k]}</b><small>${Math.round((counts[k]/Math.max(1,state.words.length))*100)}%</small></div>`));
    const hist=allHistory(7),acc=hist.length?Math.round(hist.filter(h=>h.correct).length/hist.length*100):0,mins=Math.round(hist.reduce((s,h)=>s+h.ms,0)/60000);
    document.getElementById('weeklyAnswers').textContent=hist.length;document.getElementById('weeklyAccuracy').textContent=hist.length?`${acc}%`:'—';document.getElementById('weeklyMinutes').textContent=mins;
    const mb=document.getElementById('miniBars'),bs=dayBuckets(7),max=Math.max(1,...bs.map(x=>x.c));bs.forEach(x=>mb.insertAdjacentHTML('beforeend',`<div class="mini-bar-wrap"><div class="mini-bar" style="height:${Math.max(5,x.c/max*60)}px"></div><small>${x.label}</small></div>`));
    document.getElementById('startSession').onclick=()=>startSession(false);document.getElementById('quickReview').onclick=()=>startSession(true);
  }

  function startSession(reviewOnly){const words=selectSession(state.settings.sessionSize,reviewOnly);state.session={queue:[...words],initial:words.length,done:0,correct:0,wrong:0,startedAt:now(),phase:'card',current:null,questionStarted:0,cardRevealed:false};route('learn')}

  function renderLearn(app){app.append(clone('learnTemplate'));document.querySelector('.bottom-nav').style.display=state.session?'none':'';document.getElementById('exitSession').onclick=()=>{state.session=null;document.querySelector('.bottom-nav').style.display='grid';route('home')};if(!state.session||!state.session.queue.length){renderSessionResult();return}renderNextStudy();}
  function renderNextStudy(){const s=state.session;if(!s.current)s.current=s.queue.shift();const w=s.current;const stage=document.getElementById('learnStage');document.getElementById('sessionDone').textContent=s.done;document.getElementById('sessionTotal').textContent=s.initial;document.getElementById('sessionProgressBar').style.width=`${clamp(s.done/Math.max(1,s.initial)*100,0,100)}%`;
    if(s.phase==='card')renderCard(stage,w);else renderQuiz(stage,w);
  }
  function renderCard(stage,w){stage.innerHTML=`<article class="study-card"><span class="level-tag">${esc(w.level||w.part_of_speech||'WORD')}</span><div class="pronunciation">${esc(w.part_of_speech)}</div><div class="study-word">${esc(w.word)}</div><div class="pronunciation">${esc(w.pronunciation)}</div><button class="speak-button" id="speakWord">♬</button><div id="cardMeaning" style="display:none"><div class="study-meaning">${esc(w.meaning)}</div><div class="example">${esc(w.example)}</div></div></article><button id="revealCard" class="primary-button reveal-button">答えを見る</button><div class="card-actions" id="cardActions" style="display:none"><button class="unknown">← わからない</button><button class="known">覚えた →</button></div>`;
    const speak=()=>speakWord(w.word);document.getElementById('speakWord').onclick=speak;if(state.settings.autoSpeak)speak();document.getElementById('revealCard').onclick=()=>{document.getElementById('cardMeaning').style.display='block';document.getElementById('cardActions').style.display='grid';document.getElementById('revealCard').style.display='none'};
    document.querySelector('.unknown').onclick=()=>{state.progress[w.id].cardKnown=false;s.phase='quiz';s.questionStarted=now();renderNextStudy()};document.querySelector('.known').onclick=()=>{state.progress[w.id].cardKnown=true;s.phase='quiz';s.questionStarted=now();renderNextStudy()};
  }
  function distractorsFor(w){const same=state.words.filter(x=>x.id!==w.id&&x.part_of_speech===w.part_of_speech);const pool=same.length>=3?same:state.words.filter(x=>x.id!==w.id);return shuffle(pool).slice(0,3).map(x=>x.meaning)}
  function renderQuiz(stage,w){const choices=shuffle([w.meaning,...distractorsFor(w)]);stage.innerHTML=`<article class="study-card" style="justify-content:flex-start;padding-top:72px"><span class="level-tag">4 CHOICE</span><div class="study-word">${esc(w.word)}</div><div class="pronunciation">${esc(w.pronunciation)}</div><div class="choice-grid">${choices.map((c,i)=>`<button class="choice" data-choice="${esc(c)}"><span style="color:#aaa;margin-right:9px">${i+1}</span>${esc(c)}</button>`).join('')}</div><div id="feedback"></div></article>`;
    document.querySelectorAll('.choice').forEach(btn=>btn.onclick=()=>answerChoice(btn,w));
  }
  function answerChoice(btn,w){if(document.querySelector('.continue-button'))return;const chosen=btn.dataset.choice,correct=chosen===w.meaning,ms=Math.max(250,now()-state.session.questionStarted);document.querySelectorAll('.choice').forEach(b=>{b.disabled=true;if(b.dataset.choice===w.meaning)b.classList.add('correct');else if(b===btn)b.classList.add('wrong')});
    updateMemory(w.id,correct,ms);const s=state.session;if(correct)s.correct++;else{s.wrong++;const insert=Math.min(s.queue.length,2+Math.floor(Math.random()*4));s.queue.splice(insert,0,w)}
    const fb=document.getElementById('feedback');fb.innerHTML=`<div class="feedback-box"><b>${correct?'正解':'もう一度'}</b><p>${esc(w.meaning)}${w.example?` · ${esc(w.example)}`:''}</p></div><button class="primary-button continue-button">次へ</button>`;
    document.querySelector('.continue-button').onclick=()=>{s.done++;s.current=null;s.phase='card';if(s.done>=s.initial&&s.queue.length===0)renderSessionResult();else renderNextStudy()};
  }
  function renderSessionResult(){const s=state.session,stage=document.getElementById('learnStage');document.getElementById('sessionDone').textContent=s?.done||0;document.getElementById('sessionProgressBar').style.width='100%';const total=(s?.correct||0)+(s?.wrong||0),acc=total?Math.round(s.correct/total*100):0,mins=Math.max(1,Math.round((now()-(s?.startedAt||now()))/60000));stage.innerHTML=`<div class="session-result"><div class="result-orb">✓</div><p class="eyebrow">SESSION COMPLETE</p><h1>おつかれさまでした</h1><p class="muted">忘れやすい単語は、次回も優先して出題されます。</p><div class="result-stats"><div class="result-stat"><b>${total}</b><small>回答</small></div><div class="result-stat"><b>${acc}%</b><small>正答率</small></div><div class="result-stat"><b>${mins}</b><small>分</small></div></div><button class="primary-button" id="finishSession">ホームへ戻る</button></div>`;document.getElementById('finishSession').onclick=()=>{state.session=null;document.querySelector('.bottom-nav').style.display='grid';route('home')};}
  function speakWord(text){if(!('speechSynthesis'in window))return;speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang='en-US';u.rate=.88;speechSynthesis.speak(u)}

  function renderWords(app){app.append(clone('wordsTemplate'));document.getElementById('wordsTotal').textContent=state.words.length;const search=document.getElementById('wordSearch'),filter=document.getElementById('masteryFilter');const draw=()=>{const q=search.value.trim().toLowerCase(),f=filter.value;const list=state.words.filter(w=>{const p=state.progress[w.id];return(f==='all'||p.mastery===f)&&(!q||`${w.word} ${w.meaning} ${w.tags}`.toLowerCase().includes(q))});document.getElementById('wordList').innerHTML=list.length?list.map(w=>{const p=state.progress[w.id],m=MASTERY[p.mastery];return`<div class="word-item"><div class="word-main"><b>${esc(w.word)}</b><span>${esc(w.meaning)}${w.part_of_speech?` · ${esc(w.part_of_speech)}`:''}</span></div><span class="status-pill ${p.mastery}">${m.label}</span></div>`}).join(''):'<div class="empty">該当する単語はありません。</div>'};search.oninput=draw;filter.onchange=draw;draw()}
  function renderStats(app){app.append(clone('statsTemplate'));const hist=allHistory(30),acc=hist.length?Math.round(hist.filter(h=>h.correct).length/hist.length*100):0,mastered=state.words.filter(w=>state.progress[w.id].mastery==='mastered').length;document.getElementById('statsCards').innerHTML=`<div class="stats-card"><b>${hist.length}</b><span>30日間の回答</span></div><div class="stats-card"><b>${acc}%</b><span>30日間の正答率</span></div><div class="stats-card"><b>${mastered}</b><span>覚えた単語</span></div><div class="stats-card"><b>${streakDays()}</b><span>連続学習日数</span></div>`;
    const bs=dayBuckets(7),max=Math.max(1,...bs.map(x=>x.c));document.getElementById('weekChart').innerHTML=bs.map(x=>`<div class="week-bar-wrap"><div class="week-bar" title="${x.c}回答" style="height:${Math.max(5,x.c/max*112)}px"></div><small>${x.label}</small></div>`).join('');
    const counts={weak:0,fuzzy:0,almost:0,mastered:0};state.words.forEach(w=>counts[state.progress[w.id].mastery]++);document.getElementById('masteryBreakdown').innerHTML=Object.entries(MASTERY).map(([k,m])=>`<div class="breakdown-row"><span>${m.label}</span><div class="breakdown-track"><div class="breakdown-fill" style="width:${counts[k]/Math.max(1,state.words.length)*100}%;background:${m.color}"></div></div><b>${counts[k]}</b></div>`).join('')}
  function renderSettings(app){app.append(clone('settingsTemplate'));document.getElementById('sheetUrl').value=state.settings.sheetCsvUrl;document.getElementById('dailyGoalInput').value=state.settings.dailyGoal;document.getElementById('sessionSizeInput').value=state.settings.sessionSize;document.getElementById('autoSpeak').checked=state.settings.autoSpeak;document.getElementById('includeNew').checked=state.settings.includeNew;
    document.getElementById('saveSettings').onclick=async()=>{state.settings.sheetCsvUrl=document.getElementById('sheetUrl').value.trim();state.settings.dailyGoal=Number(document.getElementById('dailyGoalInput').value)||20;state.settings.sessionSize=Number(document.getElementById('sessionSizeInput').value)||20;state.settings.autoSpeak=document.getElementById('autoSpeak').checked;state.settings.includeNew=document.getElementById('includeNew').checked;saveSettings();await loadWords(true);route('home')};
    document.getElementById('resetProgress').onclick=async()=>{if(confirm('この端末の学習履歴をすべて削除しますか？')){await window.LingoDeckDB.del(PROGRESS_KEY);state.progress={};ensureProgress();render()}}
  }

  document.querySelectorAll('.nav-item').forEach(b=>b.onclick=()=>route(b.dataset.route));
  document.getElementById('syncButton').onclick=()=>loadWords(true);
  if('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(()=>{});
  (async function boot(){
    state.progress = await window.LingoDeckDB.get(PROGRESS_KEY, {});
    await loadWords();
  })();
})();
