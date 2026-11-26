import {useEffect,useState,type FormEvent} from 'react';
import {allItems,api,type CalendarEvent,type Task,type Profile} from './api';
import {candidates,dayShift,dayStart,instant,localTime,pretty,validDay} from './time';

const stateNames:Record<Task['status'],string>={pending:'待完成',in_progress:'进行中',done:'已完成',cancelled:'已取消'};
const priorityNames={low:'低',normal:'普通',high:'高'};
const transitions:Record<Task['status'],Task['status'][]>={pending:['pending','in_progress','done','cancelled'],in_progress:['in_progress','pending','done','cancelled'],done:['done','pending'],cancelled:['cancelled','pending']};
function message(e:unknown){return e instanceof Error?e.message:'操作未完成，请重试。';}
function TimeField({label,value,set,zone,choice,setChoice,required=true}:{label:string;value:string;set:(v:string)=>void;zone:string;choice:string;setChoice:(v:string)=>void;required?:boolean}){
  const matches=value?candidates(value,zone):[];
  return <div className="field"><label>{label}<input type="datetime-local" required={required} value={value} onChange={e=>{set(e.target.value);setChoice('');}}/></label>{matches.length>1&&<label>重复时刻（{label}）<select value={choice} onChange={e=>setChoice(e.target.value)} required><option value="">请选择具体时刻</option>{matches.map((v,i)=><option value={v} key={v}>{i===0?'较早':'较晚'}一次 · UTC {v.slice(11,16)}</option>)}</select></label>}</div>;
}
function Result({error,notice}:{error:string;notice:string}){return <>{error&&<div role="alert" className="alert error">{error}</div>}{notice&&<div role="status" className="alert success">{notice}</div>}</>;}

export function CalendarPage({profile}:{profile:Profile}){
  const zone=profile.user.timezone,today=localTime(new Date(),zone).slice(0,10);
  const params=new URLSearchParams(location.hash.split('?')[1]||'');
  const initialDay=params.get('date')||'';
  const [anchor,setAnchor]=useState(validDay(initialDay)?initialDay:today),[view,setView]=useState<'week'|'month'>(params.get('view')==='month'?'month':'week'),[showCancelled,setShowCancelled]=useState(false);
  const [items,setItems]=useState<CalendarEvent[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
  const [editing,setEditing]=useState<CalendarEvent|null|undefined>(undefined);
  useEffect(()=>{history.replaceState(null,'','#/calendar?'+new URLSearchParams({date:anchor,view}));},[anchor,view]);
  let start=anchor,end=anchor;
  if(view==='week'){
    const weekday=new Date(anchor+'T12:00:00Z').getUTCDay();start=dayShift(anchor,-((weekday+6)%7));end=dayShift(start,7);
  }else{start=anchor.slice(0,7)+'-01';const d=new Date(start+'T12:00:00Z');d.setUTCMonth(d.getUTCMonth()+1);end=d.toISOString().slice(0,10);}
  useEffect(()=>{let active=true;setLoading(true);setError('');
    const qs=new URLSearchParams({start:dayStart(start,zone),end:dayStart(end,zone)});
    allItems<CalendarEvent>('/events?'+qs).then(v=>{if(active)setItems(v);}).catch(e=>{if(active)setError(message(e));}).finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[start,end,zone,revision]);
  async function change(item:CalendarEvent){if(busy)return;const cancelling=item.status==='active';if(cancelling&&!confirm('取消这个日程？关联待办会保留。'))return;setBusy(true);setError('');setNotice('');
    try{await api('/events/'+item.id,{version:item.version,...(cancelling?{}:{status:'active'})},cancelling?'DELETE':'PATCH');setNotice(cancelling?'日程已取消，关联待办保留':'日程已恢复');setRevision(v=>v+1);if(editing?.id===item.id)setEditing(undefined);}catch(e){setError(message(e));}finally{setBusy(false);}}
  const days:string[]=[];for(let d=start;d<end;d=dayShift(d,1))days.push(d);
  const visible=items.filter(e=>showCancelled||e.status==='active');
  return <><div className="page-heading"><div><span className="overline">MAKE TIME FOR WHAT MATTERS</span><h1>日程</h1><p>时间按 {zone} 展示，重叠日程会在保存时提示。</p></div><button className="primary" onClick={()=>{setEditing(null);setNotice('');}}>新建日程</button></div>
    <Result error={error} notice={notice}/><div className="planner-toolbar"><div className="segmented"><button aria-pressed={view==='week'} onClick={()=>setView('week')}>周视图</button><button aria-pressed={view==='month'} onClick={()=>setView('month')}>月视图</button></div><label>查看日期<input aria-label="查看日期" type="date" min="0001-01-01" max="9998-12-31" required value={anchor} onChange={e=>{if(validDay(e.target.value))setAnchor(e.target.value);}}/></label><button className="secondary" onClick={()=>setAnchor(today)}>今天</button><button className="secondary" disabled={loading} onClick={()=>setRevision(v=>v+1)}>刷新日程</button><label className="check-label"><input type="checkbox" checked={showCancelled} onChange={e=>setShowCancelled(e.target.checked)}/>显示已取消</label></div>
    {editing!==undefined&&<EventForm key={editing?.id||'new'} event={editing} zone={zone} day={anchor} onClose={()=>setEditing(undefined)} onSaved={()=>{setEditing(undefined);setNotice('日程已保存');setRevision(v=>v+1);}}/>}
    <p className="range-label">{start} — {dayShift(end,-1)} · {loading?'正在加载…':`${visible.length} 个日程`}</p>
    {!loading&&error&&<p className="muted">未能加载最新日程，请点击“刷新日程”重试。</p>}
    <div className={'calendar-grid '+view} aria-busy={loading}>{!loading&&!error&&days.map(day=>{
      const from=dayStart(day,zone),to=dayStart(dayShift(day,1),zone);
      const events=visible.filter(e=>new Date(e.start_at)<new Date(to)&&new Date(e.end_at)>new Date(from));
      return <section className={'calendar-day '+(day===today?'today':'')+' offset-'+((new Date(day+'T12:00Z').getUTCDay()+6)%7)} key={day}><h2>{day.slice(5)} <small>{new Intl.DateTimeFormat('zh-CN',{weekday:'short',timeZone:'UTC'}).format(new Date(day+'T12:00Z'))}</small></h2>{events.length===0&&<p className="empty-day">留一点空白</p>}{events.map(event=><article className={'event-card '+event.status} key={event.id}><span className="small-pill">{event.status==='cancelled'?'已取消':'日程'}</span><h3>{event.title}</h3><p>{pretty(event.start_at,zone)} — {pretty(event.end_at,zone)}</p>{event.description&&<p className="item-description">{event.description}</p>}<div className="item-actions"><button disabled={busy} onClick={()=>setEditing(event)}>编辑</button><button disabled={busy} onClick={()=>void change(event)}>{event.status==='active'?'取消日程':'恢复日程'}</button></div></article>)}</section>;
    })}</div></>;
}
function EventForm({event,zone,day,onClose,onSaved}:{event:CalendarEvent|null;zone:string;day:string;onClose:()=>void;onSaved:()=>void}){
  const [title,setTitle]=useState(event?.title||''),[description,setDescription]=useState(event?.description||''),[start,setStart]=useState(event?localTime(event.start_at,zone):day+'T09:00'),[end,setEnd]=useState(event?localTime(event.end_at,zone):day+'T10:00');
  const [startChoice,setStartChoice]=useState(event?.start_at?new Date(event.start_at).toISOString():''),[endChoice,setEndChoice]=useState(event?.end_at?new Date(event.end_at).toISOString():'');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function submit(e:FormEvent){e.preventDefault();if(busy)return;setBusy(true);setError('');try{
    const start_at=instant(start,zone,startChoice),end_at=instant(end,zone,endChoice);
    if(end_at<=start_at)throw new Error('结束时间必须晚于开始时间');
    await api(event?'/events/'+event.id:'/events',{title,description,start_at,end_at,...(event?{version:event.version}:{})},event?'PATCH':'POST');onSaved();
  }catch(e){setError(message(e));}finally{setBusy(false);}}
  return <section className="panel editor"><h2>{event?'编辑日程':'新建日程'}</h2><form onSubmit={submit}><Result error={error} notice=""/><div className="field"><label>日程标题<input required maxLength={200} value={title} onChange={e=>setTitle(e.target.value)}/></label></div><div className="form-columns"><TimeField label="开始时间" value={start} set={setStart} zone={zone} choice={startChoice} setChoice={setStartChoice}/><TimeField label="结束时间" value={end} set={setEnd} zone={zone} choice={endChoice} setChoice={setEndChoice}/></div><div className="field"><label>日程备注<textarea maxLength={4000} value={description} onChange={e=>setDescription(e.target.value)}/></label></div><div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={onClose}>放弃编辑</button><button className="primary" disabled={busy||!title.trim()}>{busy?'保存中…':'保存日程'}</button></div></form></section>;
}

export function TasksPage({profile}:{profile:Profile}){
  const zone=profile.user.timezone,today=localTime(new Date(),zone).slice(0,10);
  const [items,setItems]=useState<Task[]>([]),[status,setStatus]=useState('all'),[date,setDate]=useState('all'),[revision,setRevision]=useState(0),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [editing,setEditing]=useState<Task|null|undefined>(undefined);
  useEffect(()=>{let active=true;setLoading(true);setError('');const q=new URLSearchParams();if(status!=='all')q.set('status',status);
    if(date==='today'){q.set('due_start',dayStart(today,zone));q.set('due_end',dayStart(dayShift(today,1),zone));}
    if(date==='week'){q.set('due_start',dayStart(today,zone));q.set('due_end',dayStart(dayShift(today,7),zone));}
    if(date==='overdue')q.set('due_end',new Date().toISOString());
    allItems<Task>('/tasks?'+q).then(v=>{if(active)setItems(v);}).catch(e=>{if(active)setError(message(e));}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};
  },[status,date,revision,zone,today]);
  async function update(item:Task,next?:Task['status']){if(busy)return;if(!next&&!confirm('永久删除这条待办？此操作无法撤销。'))return;setBusy(true);setError('');setNotice('');try{await api('/tasks/'+item.id,{version:item.version,...(next?{status:next}:{})},next?'PATCH':'DELETE');setNotice(next?'待办状态已更新':'待办已删除');setRevision(v=>v+1);if(editing?.id===item.id)setEditing(undefined);}catch(e){setError(message(e));}finally{setBusy(false);}}
  const visible=items.filter(v=>date!=='none'||!v.due_at).filter(v=>date!=='overdue'||['pending','in_progress'].includes(v.status));
  return <><div className="page-heading"><div><span className="overline">ONE THING AT A TIME</span><h1>待办</h1><p>把事情记下来，一件一件完成。时区：{zone}</p></div><button className="primary" onClick={()=>{setEditing(null);setNotice('');}}>新建待办</button></div><Result error={error} notice={notice}/>
    <div className="planner-toolbar"><label>筛选状态<select value={status} onChange={e=>setStatus(e.target.value)}><option value="all">全部状态</option>{Object.entries(stateNames).map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label><label>截止日期<select value={date} onChange={e=>setDate(e.target.value)}><option value="all">全部日期</option><option value="today">今天</option><option value="week">未来七天</option><option value="overdue">已逾期且未完成</option><option value="none">无截止时间</option></select></label><button className="secondary" disabled={loading} onClick={()=>setRevision(v=>v+1)}>刷新待办</button></div>
    {editing!==undefined&&<TaskForm key={editing?.id||'new'} task={editing} zone={zone} onClose={()=>setEditing(undefined)} onSaved={()=>{setEditing(undefined);setNotice('待办已保存');setRevision(v=>v+1);}}/>}
    {loading?<p className="muted">正在加载待办…</p>:error?<p className="muted">请刷新重试，编辑内容会保留。</p>:<div className="task-list">{visible.length===0&&<section className="panel empty-state"><h2>暂时没有符合条件的待办</h2><p>试试其他筛选，或记下接下来想做的一件事。</p></section>}{visible.map(item=><article className={'panel task-card '+item.status} key={item.id}><div className="task-info"><span className={'small-pill priority-'+item.priority}>{priorityNames[item.priority]}优先级 · {stateNames[item.status]}</span><h2>{item.title}</h2>{item.description&&<p className="item-description">{item.description}</p>}<p className={item.due_at&&new Date(item.due_at)<new Date()&&!['done','cancelled'].includes(item.status)?'overdue':''}>{item.due_at?'截止 '+pretty(item.due_at,zone):'未设置截止时间'}{item.event_id?' · 已关联日程':''}</p></div><div className="item-actions"><button disabled={busy} onClick={()=>setEditing(item)}>编辑待办</button>{['done','cancelled'].includes(item.status)?<button disabled={busy} onClick={()=>void update(item,'pending')}>重新打开</button>:<><button disabled={busy} onClick={()=>void update(item,'done')}>标记完成</button><button disabled={busy} onClick={()=>void update(item,'cancelled')}>取消待办</button></>}<button className="danger" disabled={busy} onClick={()=>void update(item)}>删除待办</button></div></article>)}</div>}</>;
}
function TaskForm({task,zone,onClose,onSaved}:{task:Task|null;zone:string;onClose:()=>void;onSaved:()=>void}){
  const [title,setTitle]=useState(task?.title||''),[description,setDescription]=useState(task?.description||''),[due,setDue]=useState(task?.due_at?localTime(task.due_at,zone):''),[choice,setChoice]=useState(task?.due_at?new Date(task.due_at).toISOString():''),[priority,setPriority]=useState(task?.priority||'normal'),[status,setStatus]=useState<Task['status']>(task?.status||'pending'),[eventId,setEventId]=useState(task?.event_id||'');
  const [events,setEvents]=useState<CalendarEvent[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[linksError,setLinksError]=useState('');
  useEffect(()=>{let active=true;const now=new Date(),from=new Date(now);from.setUTCMonth(from.getUTCMonth()-6);const to=new Date(from);to.setUTCFullYear(to.getUTCFullYear()+1);
    allItems<CalendarEvent>('/events?'+new URLSearchParams({start:from.toISOString(),end:to.toISOString()})).then(v=>{if(active)setEvents(v);}).catch(()=>{if(active)setLinksError('日程列表暂不可用，可以不关联日程后保存。');});return()=>{active=false;};},[]);
  async function submit(e:FormEvent){e.preventDefault();if(busy)return;setBusy(true);setError('');try{await api(task?'/tasks/'+task.id:'/tasks',{title,description,priority,due_at:due?instant(due,zone,choice):null,event_id:eventId||null,...(task?{version:task.version,status}:{})},task?'PATCH':'POST');onSaved();}catch(e){setError(message(e));}finally{setBusy(false);}}
  return <section className="panel editor"><h2>{task?'编辑待办':'新建待办'}</h2><form onSubmit={submit}><Result error={error} notice=""/><div className="field"><label>待办标题<input required maxLength={200} value={title} onChange={e=>setTitle(e.target.value)}/></label></div><TimeField label="截止时间" value={due} set={setDue} zone={zone} choice={choice} setChoice={setChoice} required={false}/><div className="form-columns"><div className="field"><label>优先级<select value={priority} onChange={e=>setPriority(e.target.value as Task['priority'])}>{Object.entries(priorityNames).map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label></div>{task&&<div className="field"><label>待办状态<select value={status} onChange={e=>setStatus(e.target.value as Task['status'])}>{transitions[task.status].map(v=><option key={v} value={v}>{stateNames[v]}</option>)}</select></label></div>}</div><div className="field"><label>关联日程（可选）<select value={eventId} onChange={e=>setEventId(e.target.value)}><option value="">不关联</option>{eventId&&!events.some(v=>v.id===eventId)&&<option value={eventId}>保留原关联日程</option>}{events.map(v=><option key={v.id} value={v.id}>{v.title} · {pretty(v.start_at,zone)}{v.status==='cancelled'?'（已取消）':''}</option>)}</select></label><small>{linksError||'可选择前后半年内的日程。取消日程不会删除这条待办。'}</small></div><div className="field"><label>待办备注<textarea maxLength={4000} value={description} onChange={e=>setDescription(e.target.value)}/></label></div><div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={onClose}>放弃编辑</button><button className="primary" disabled={busy||!title.trim()}>{busy?'保存中…':'保存待办'}</button></div></form></section>;
}

export function HomeAgenda({profile}:{profile:Profile}){
  const [events,setEvents]=useState<CalendarEvent[]>([]),[tasks,setTasks]=useState<Task[]>([]),[error,setError]=useState(''),[ready,setReady]=useState(false),[revision,setRevision]=useState(0);
  const zone=profile.user.timezone,today=localTime(new Date(),zone).slice(0,10);
  useEffect(()=>{let active=true;setReady(false);setError('');Promise.all([allItems<CalendarEvent>('/events?'+new URLSearchParams({start:dayStart(today,zone),end:dayStart(dayShift(today,1),zone),status:'active'})),allItems<Task>('/tasks')]).then(([e,t])=>{if(active){setEvents(e);setTasks(t.filter(v=>['pending','in_progress'].includes(v.status)));setReady(true);}}).catch(e=>{if(active)setError(message(e));});return()=>{active=false;};},[zone,today,revision]);
  return <section className="panel agenda"><div className="section-title"><h2>今天与接下来</h2><button className="text-button" onClick={()=>setRevision(v=>v+1)}>刷新概览</button></div>{error?<div role="alert" className="alert error">{error}</div>:!ready?<p className="muted">正在整理日程和待办…</p>:<><div className="agenda-counts"><a href="#/calendar"><strong>{events.length}</strong> 今日日程</a><a href="#/tasks"><strong>{tasks.length}</strong> 未完成待办</a></div><div className="agenda-lists"><div><h3>今日日程</h3>{events.length===0?<p className="muted">今天还没有日程。</p>:events.map(v=><a className="agenda-row" key={v.id} href="#/calendar"><span>{v.title}</span><small>{pretty(v.start_at,zone)}</small></a>)}</div><div><h3>近期待办</h3>{tasks.length===0?<p className="muted">暂时没有未完成待办。</p>:tasks.slice(0,5).map(v=><a className="agenda-row" key={v.id} href="#/tasks"><span>{v.title}</span><small>{v.due_at?pretty(v.due_at,zone):'无截止时间'}</small></a>)}</div></div></>}</section>;
}
