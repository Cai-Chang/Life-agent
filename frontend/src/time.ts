// Civil input belongs to the user's configured zone, independent of device zone.
export function localTime(value:string|Date,zone:string) {
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value));
  const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
export function candidates(value:string,zone:string):string[] {
  if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value))return [];
  const civil=Date.parse(value+'Z'),result:string[]=[];
  if(!Number.isFinite(civil))return [];
  for(let offset=-14*60;offset<=14*60;offset+=15){
    const instant=new Date(civil-offset*60000);
    if(localTime(instant,zone)===value)result.push(instant.toISOString());
  }
  return result.sort();
}
export function instant(value:string,zone:string,choice=''):string {
  const matches=candidates(value,zone);
  if(!matches.length)throw new Error('这个本地时间不存在，请检查日期或夏令时跳变，选择其他时间。');
  if(matches.length>1&&!matches.includes(choice))throw new Error('这个时间因夏令时出现两次，请选择具体时刻。');
  return matches.length===1?matches[0]:choice;
}
export function dayShift(day:string,amount:number){return new Date(Date.parse(day+'T12:00:00Z')+amount*86400000).toISOString().slice(0,10);}
export function dayStart(day:string,zone:string){
  // Midnight transitions exist in a few zones: choose the first valid minute.
  for(let m=0;m<180;m++){
    const v=`${day}T${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;
    const found=candidates(v,zone);if(found.length)return found[0];
  }
  throw new Error('该时区的日期无效，请选择其他日期。');
}
export function pretty(value:string,zone:string){return new Intl.DateTimeFormat('zh-CN',{timeZone:zone,month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));}
