import {useEffect, useState, type FormEvent, type ReactNode} from 'react';
import {api, ApiError, setSession, type Profile, type Workspace} from './api';
import {CalendarPage,TasksPage,HomeAgenda} from './Planning';
import {ChatPage,ModelSettingsPanel} from './Chat';

const zones = ['Asia/Shanghai','Asia/Hong_Kong','Asia/Taipei','Asia/Tokyo','Asia/Singapore','Asia/Kolkata','Europe/London','Europe/Paris','America/New_York','America/Los_Angeles','Australia/Sydney','Pacific/Auckland','UTC'];
function ZoneSelect({value,onChange}: {value:string;onChange:(value:string)=>void}) {
  return <select id="timezone" value={value} onChange={e=>onChange(e.target.value)}>{[...new Set([...zones,value])].map(zone=><option key={zone}>{zone}</option>)}</select>;
}
function Icon({name,size=20}: {name:string;size?:number}) {
  const paths:Record<string,ReactNode> = {
    chat:<><path d="M4 4h16v12H9l-5 4Z"/><path d="M8 8h8M8 12h5"/></>,
    calendar:<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/></>,
    tasks:<><path d="m3 6 2 2 3-4m3 2h10M3 13l2 2 3-4m3 2h10M3 20h18"/></>,
    home:<><path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/></>,
    space:<><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18M9 9v11"/></>,
    settings:<><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/></>,
    shield:<><path d="M12 3 4 6v6c0 4 8 9 8 9s8-5 8-9V6Z"/><path d="m8 12 3 3 5-6"/></>,
    clock:<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    logout:<><path d="M10 4H4v16h6M9 12h12m-4-4 4 4-4 4"/></>,
    leaf:<><path d="M6 19C2 9 9 3 20 3c0 11-6 18-14 16Z"/><path d="M4 21 15 10"/></>,
    eye:<><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></>,
    check:<path d="m5 12 4 4L19 6"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.leaf}</svg>;
}
function Brand({light=false}: {light?:boolean}) {return <a href="#/" className={`brand ${light?'light':''}`} aria-label="LifeAgent 首页"><span className="brand-mark"><Icon name="leaf" size={25}/></span><span>LifeAgent<small>让生活，有自己的节奏</small></span></a>;}

function AuthPage({mode,onLogin,banner=''}: {mode:'login'|'register';onLogin:(profile:Profile)=>void;banner?:string}) {
  const register=mode==='register';
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[name,setName]=useState('');
  const [zone,setZone]=useState(Intl.DateTimeFormat().resolvedOptions().timeZone||'Asia/Shanghai');
  const [visible,setVisible]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  async function submit(event:FormEvent) {
    event.preventDefault();if(busy)return;setBusy(true);setError('');
    try {const profile=await api<Profile>(register?'/auth/register':'/auth/login',register?{email,password,display_name:name,timezone:zone}:{email,password});onLogin(profile);}
    catch(e){setError(e instanceof Error?e.message:'操作未完成');}finally{setBusy(false);}
  }
  return <main className="auth-layout"><section className="auth-story"><Brand light/><div className="story-content"><span className="overline">YOUR SPACE. YOUR PACE.</span><h1>生活的主角，<br/>始终是你。</h1><p>从一个属于自己的空间开始，<br/>为日常留一点清晰，为自己留一点余地。</p><div className="orbit-art" aria-hidden="true"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="orbit-core"><Icon name="leaf" size={62}/></div><div className="orbit-note note-one"><Icon name="shield"/>只属于你的空间</div><div className="orbit-note note-two"><Icon name="clock"/>按你的时区生活</div><span className="orbit-star">✳</span></div></div><div className="story-footer">A little more clarity. A little more life.</div></section>
    <section className="auth-main"><div className="auth-top">{register?'已经拥有账号？':'初次来到这里？'} <a href={register?'#/login':'#/register'}>{register?'直接登录':'创建账号'}</a></div><div className="auth-form-wrap"><span className="small-pill">个人空间 · V0.1</span><h2>{register?'开启你的生活空间':'欢迎回来'}</h2><p className="muted">{register?'创建账号，你的个人空间会同时准备好。':'登录 LifeAgent，回到属于你的日常。'}</p>
    <form onSubmit={submit} className="auth-form">{register&&<div className="field"><label htmlFor="display-name">昵称</label><input id="display-name" autoComplete="nickname" required minLength={1} maxLength={100} value={name} onChange={e=>setName(e.target.value)} placeholder="希望我们怎么称呼你"/></div>}
      <div className="field"><label htmlFor="email">邮箱</label><input id="email" type="email" autoComplete="email" required maxLength={320} value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com"/></div>
      <div className="field"><label htmlFor="password">密码</label><div className="password-field"><input id="password" type={visible?'text':'password'} autoComplete={register?'new-password':'current-password'} required minLength={register?12:1} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)} placeholder={register?'至少 12 个字符':'输入你的密码'}/><button type="button" aria-label={visible?'隐藏密码':'显示密码'} onClick={()=>setVisible(!visible)}><Icon name="eye"/></button></div>{register&&<small>支持长密码或密码短语，请勿重复使用其他账号的密码。</small>}</div>
      {register&&<div className="field"><label htmlFor="timezone">你的时区</label><ZoneSelect value={zone} onChange={setZone}/></div>}
      {(error||banner)&&<div className="alert error" role="alert">{error||banner}</div>}
      <button className="primary full" disabled={busy} type="submit">{busy?'正在处理…':register?'创建账号并进入空间':'登录'}</button>
    </form><div className="auth-privacy"><Icon name="shield" size={16}/><span>个人空间默认仅你可见，密码不会明文保存。</span></div></div><div className="auth-bottom">LifeAgent · 个人与家庭智能管家</div></section></main>;
}

function App() {
  const [profile,setProfile]=useState<Profile|null>(null),[phase,setPhase]=useState<'loading'|'ready'|'error'>('loading');
  const [route,setRoute]=useState(location.hash.slice(1)||'/');
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const [authNotice,setAuthNotice]=useState('');
  useEffect(()=>{const handle=()=>{setRoute(location.hash.slice(1)||'/');setError('');setNotice('');};window.addEventListener('hashchange',handle);return()=>window.removeEventListener('hashchange',handle);},[]);
  function accept(data:Profile|null){setSession(data);setProfile(data);}
  async function restore(){setPhase('loading');try{accept(await api<Profile>('/me'));setPhase('ready');}catch(e){if(e instanceof ApiError&&e.status===401){accept(null);setPhase('ready');}else{setError(e instanceof Error?e.message:'服务暂不可用');setPhase('error');}}}
  useEffect(()=>{void restore();const expired=()=>{accept(null);setAuthNotice('登录已失效，请重新登录。');location.hash='/login';};window.addEventListener('session-expired',expired);return()=>window.removeEventListener('session-expired',expired);},[]);
  async function save(operation:()=>Promise<void>,success='已保存') {
    if(busy)return;setBusy(true);setError('');setNotice('');
    try{await operation();setNotice(success);}catch(e){if(e instanceof ApiError&&e.status===401){accept(null);setAuthNotice('登录已失效，请重新登录。');location.hash='/login';}setError(e instanceof Error?e.message:'操作未完成');}finally{setBusy(false);}
  }
  if(phase!=='ready')return <main className="boot"><Brand/><div className="boot-card"><Icon name="leaf" size={40}/><h1>{phase==='loading'?'正在打开你的空间':'暂时无法打开空间'}</h1><p>{phase==='loading'?'稍等一下，正在恢复登录状态。':error}</p>{phase==='error'&&<button className="primary" onClick={()=>void restore()}>重新连接</button>}</div></main>;
  if(!profile)return <AuthPage key={route==='/register'?'register':'login'} mode={route==='/register'?'register':'login'} banner={authNotice} onLogin={data=>{accept(data);setAuthNotice('');location.hash='/';}}/>;
  const page=route==='/space'?'space':route==='/settings'?'settings':route.startsWith('/chat')?'chat':route.startsWith('/calendar')?'calendar':route==='/tasks'?'tasks':'home';
  const name=profile.user.display_name, date=new Intl.DateTimeFormat('zh-CN',{timeZone:profile.user.timezone,month:'long',day:'numeric',weekday:'long'}).format(new Date());
  const hours=Number(new Intl.DateTimeFormat('en-GB',{timeZone:profile.user.timezone,hour:'2-digit',hour12:false}).format(new Date()));
  const greeting=hours<6?'夜深了':hours<12?'上午好':hours<18?'下午好':'晚上好';
  return <div className="app-layout"><aside className="sidebar"><Brand/><div className="nav-section-label">我的 LifeAgent</div><nav>{[['home','/','概览'],['calendar','/calendar','日程'],['tasks','/tasks','待办'],['chat','/chat','AI 对话'],['space','/space','个人空间'],['settings','/settings','个人设置']].map(([icon,to,label])=><a className={page===icon?'nav-item active':'nav-item'} href={'#'+to} key={to}><Icon name={icon}/>{label}</a>)}</nav><div className="sidebar-note"><Icon name="shield" size={22}/><strong>你的空间，你的边界</strong><p>个人资料与空间仅对你开放。</p></div><div className="sidebar-user"><div className="avatar">{Array.from(name)[0]}</div><div><strong>{name}</strong><span>个人账号</span></div></div></aside>
    <main className="app-main"><header className="app-header"><div className="breadcrumb">我的空间 <span>/</span> {{home:'概览',space:'个人空间',settings:'个人设置',calendar:'日程',tasks:'待办',chat:'AI 对话'}[page]}</div><button className="logout-button" disabled={busy} onClick={()=>void save(async()=>{await api('/auth/logout',{});accept(null);location.hash='/login';},'')}><Icon name="logout" size={17}/>退出登录</button></header>
    <div className="app-content">{error&&<div className="alert error" role="alert">{error}</div>}{notice&&<div className="alert success" role="status"><Icon name="check" size={17}/>{notice}</div>}
    {page==='home'?<><div className="page-heading"><div><span className="overline">A SPACE FOR YOUR EVERYDAY</span><h1>{greeting}，{name}<span className="greeting-dot">。</span></h1><p>慢一点也没关系，让日常从清晰开始。</p></div><div className="date-chip"><Icon name="clock" size={17}/>{date}</div></div>
      <section className="welcome-banner"><div><span className="banner-label">你的个人空间</span><h2>{profile.workspace.name}</h2><p>一个属于你的地方，承载每一个认真生活的想法。</p><a className="white-button" href="#/space">管理空间</a></div><div className="banner-art" aria-hidden="true"><div/><Icon name="leaf" size={108}/><span>✳</span></div></section>
      <div className="summary-grid"><section className="summary-card"><div className="card-icon"><Icon name="space"/></div><span>当前空间</span><strong>{profile.workspace.name}</strong><small>个人空间 · 你是所有者</small></section><section className="summary-card"><div className="card-icon blue"><Icon name="clock"/></div><span>生活时区</span><strong>{profile.user.timezone}</strong><small>时间会按你的时区展示</small></section><section className="summary-card"><div className="card-icon lilac"><Icon name="shield"/></div><span>访问范围</span><strong>仅你可见</strong><small>账号与空间按用户隔离</small></section></div>
      <div className="home-lower"><section className="panel getting-started"><div className="section-title"><h2>从这里开始</h2><span>为自己整理一个小角落</span></div><a className="action-row" href="#/settings"><span className="action-icon"><Icon name="settings"/></span><div><strong>完善个人资料</strong><p>设置昵称与时区，让空间更懂你的节奏。</p></div><span className="row-label">去设置</span></a><a className="action-row" href="#/space"><span className="action-icon"><Icon name="space"/></span><div><strong>给空间取个名字</strong><p>学习、工作，或是认真生活的每一天。</p></div><span className="row-label">去管理</span></a></section><section className="panel future-card"><span className="small-pill">安排日常</span><h2>给重要的事情，留出时间。</h2><p>记下待办，安排日程，再一件一件完成。</p><div className="quick-links"><a className="white-button" href="#/calendar">打开日程</a><a className="white-button" href="#/tasks">打开待办</a><a className="white-button" href="#/chat">开始对话</a></div></section></div><HomeAgenda key={profile.user.timezone} profile={profile}/></>:
      page==='chat'?<ChatPage key={profile.user.id} profile={profile}/>:page==='calendar'?<CalendarPage key={profile.user.timezone} profile={profile}/>:page==='tasks'?<TasksPage key={profile.user.timezone} profile={profile}/>:page==='space'?<><div className="page-heading"><div><span className="overline">YOUR PERSONAL SPACE</span><h1>留一个空间，给自己。</h1><p>从名字开始，让这里成为你的生活一角。</p></div></div><section className="panel space-panel"><div className="space-emblem"><Icon name="space" size={32}/></div><span className="small-pill">个人空间</span><h2>{profile.workspace.name}</h2><p className="muted">由你拥有，仅对你开放。</p><div className="space-facts"><div><span>所有者</span><strong>{name}</strong></div><div><span>访问权限</span><strong>仅本人</strong></div><div><span>创建日期</span><strong>{new Intl.DateTimeFormat('zh-CN',{timeZone:profile.user.timezone,dateStyle:'medium'}).format(new Date(profile.workspace.created_at))}</strong></div></div><SpaceForm profile={profile} busy={busy} onSave={value=>save(async()=>{const workspace=await api<Workspace>('/workspaces/'+profile.workspace.id,{name:value},'PATCH');accept({...profile,workspace});},'空间名称已更新')}/></section></>:
      <><div className="page-heading"><div><span className="overline">MAKE YOURSELF AT HOME</span><h1>按你的方式，安排日常。</h1><p>管理个人资料与时间偏好。</p></div></div><section className="panel settings-panel"><div className="section-title"><h2>个人资料</h2><span>更改会在保存后生效</span></div><ProfileForm key={profile.user.display_name+profile.user.timezone} profile={profile} busy={busy} onSave={(display_name,timezone)=>save(async()=>{accept(await api<Profile>('/me',{display_name,timezone},'PATCH'));},'个人资料已保存')}/></section><ModelSettingsPanel/><section className="panel privacy-panel"><Icon name="shield" size={26}/><div><h2>让私密，保持私密</h2><p>你的账号与空间相互绑定。其他账号无法读取或修改你的个人空间。</p></div></section></>}
    <footer className="app-footer"><span>LifeAgent</span><span>为生活留白，为日常留序。</span></footer></div></main></div>;
}

function SpaceForm({profile,busy,onSave}:{profile:Profile;busy:boolean;onSave:(name:string)=>Promise<void>}) {
  const [value,setValue]=useState(profile.workspace.name);
  return <form className="space-form" onSubmit={e=>{e.preventDefault();void onSave(value);}}><div className="field"><label htmlFor="workspace-name">空间名称</label><input id="workspace-name" required maxLength={80} value={value} onChange={e=>setValue(e.target.value)}/></div><button className="primary" disabled={busy||!value.trim()||value===profile.workspace.name}>{busy?'保存中…':'保存空间名称'}</button></form>;
}
function ProfileForm({profile,busy,onSave}:{profile:Profile;busy:boolean;onSave:(name:string,zone:string)=>Promise<void>}) {
  const [name,setName]=useState(profile.user.display_name),[zone,setZone]=useState(profile.user.timezone);
  return <form className="profile-form" onSubmit={(e:FormEvent)=>{e.preventDefault();void onSave(name,zone);}}><div className="profile-identity"><div className="avatar large">{Array.from(profile.user.display_name)[0]}</div><div><strong>{profile.user.display_name}</strong><p>{profile.user.email}</p></div></div><div className="field"><label htmlFor="profile-name">昵称</label><input id="profile-name" required maxLength={100} value={name} onChange={e=>setName(e.target.value)}/></div><div className="field"><label htmlFor="profile-email">邮箱</label><input id="profile-email" type="email" value={profile.user.email} disabled/><small>当前版本暂不支持更改登录邮箱。</small></div><div className="field"><label htmlFor="timezone">生活时区</label><ZoneSelect value={zone} onChange={setZone}/><small>时区影响页面日期和时间的展示。</small></div><div className="form-actions"><button type="button" className="secondary" onClick={()=>{setName(profile.user.display_name);setZone(profile.user.timezone);}}>重置</button><button type="submit" className="primary" disabled={busy||!name.trim()}>{busy?'保存中…':'保存个人资料'}</button></div></form>;
}

export default App;
