// Civil input belongs to the configured zone, independent of the device zone.
const formatters=new Map<string,Intl.DateTimeFormat>();
function wallTime(value:string|Date,zone:string){
  let formatter=formatters.get(zone);
  if(!formatter){formatter=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});formatters.set(zone,formatter);}
  const p=Object.fromEntries(formatter.formatToParts(new Date(value)).map(x=>[x.type,x.value]));
  return `${p.year.padStart(4,'0')}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}
export function localTime(value:string|Date,zone:string){return wallTime(value,zone).slice(0,16);}
export function validDay(day:string){
  const stamp=Date.parse(day+'T12:00:00Z');
  return /^\d{4}-\d{2}-\d{2}$/.test(day)&&day>='0001-01-01'&&day<='9998-12-31'&&Number.isFinite(stamp)&&new Date(stamp).toISOString().slice(0,10)===day;
}
export function candidates(value:string,zone:string):string[]{
  if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value))return [];
  const civil=Date.parse(value+'Z'),offsets=new Set<number>(),result=new Set<string>();
  if(!Number.isFinite(civil))return [];
  // Derive actual offsets around the input. This includes DST folds and
  // historical second-based offsets, rather than assuming 15-minute steps.
  for(let h=-36;h<=36;h+=6){
    const seed=civil+h*3600000;
    const wall=Date.parse(wallTime(new Date(seed),zone)+'Z');
    if(Number.isFinite(wall))offsets.add(wall-seed);
  }
  for(const offset of offsets){
    const instant=new Date(civil-offset);
    if(wallTime(instant,zone)===value+':00')result.add(instant.toISOString());
  }
  return [...result].sort();
}
export function instant(value:string,zone:string,choice=''):string {
  const matches=candidates(value,zone);
  if(!matches.length)throw new Error('这个本地时间不存在，请检查日期或夏令时跳变，选择其他时间。');
  if(matches.length>1&&!matches.includes(choice))throw new Error('这个时间因夏令时出现两次，请选择具体时刻。');
  return matches.length===1?matches[0]:choice;
}
export function dayShift(day:string,amount:number){return new Date(Date.parse(day+'T12:00:00Z')+amount*86400000).toISOString().slice(0,10);}
export function dayStart(day:string,zone:string){
  // A skipped civil day has zero duration in the calendar. Its boundary equals
  // the next valid day's boundary; entering an event on it is still rejected.
  for(let skipped=0;skipped<3;skipped++){
    const next=dayShift(day,skipped);
    for(let m=0;m<180;m++){
      const found=candidates(`${next}T${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`,zone);
      if(found.length)return found[0];
    }
  }
  throw new Error('该时区的日期无效，请选择其他日期。');
}
export function pretty(value:string,zone:string){return new Intl.DateTimeFormat('zh-CN',{timeZone:zone,month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));}
