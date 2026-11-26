export interface Workspace { id: string; name: string; type: 'personal'; role: 'owner'; created_at: string; }
export interface Profile { user: {id: string; email: string; display_name: string; timezone: string; created_at: string}; workspace: Workspace; csrf_token: string; }
export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
let csrf = '';
const pendingOperations=new Map<string,string>();
export function setSession(profile: Profile | null) { csrf = profile?.csrf_token || '';if(!profile)pendingOperations.clear(); }

export async function api<T>(path: string, body?: unknown, method?: string): Promise<T> {
  let response: Response;
  const verb=method || (body===undefined?'GET':'POST');
  const business=body!==undefined && /^\/(events|tasks)(\/|$)/.test(path);
  const signature=verb+path+JSON.stringify(body);
  const key=business?(pendingOperations.get(signature)||crypto.randomUUID()):'';
  if(business)pendingOperations.set(signature,key);
  try {
    response = await fetch('/api/v1' + path, {credentials: 'same-origin', cache: 'no-store',
      method: verb,
      headers: body === undefined ? {} : {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...(key?{'Idempotency-Key':key}:{})},
      ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal: AbortSignal.timeout(15000)});
  } catch { throw new ApiError(0, '暂时连接不上服务，请检查网络后重试。'); }
  if(response.status===401&&csrf)window.dispatchEvent(new Event('session-expired'));
  if (response.status === 204) {pendingOperations.delete(signature);return undefined as T;}
  let data;
  try { data = await response.json(); } catch { throw new ApiError(response.status, '服务暂不可用，请稍后重试。'); }
  if(response.status<500 && business)pendingOperations.delete(signature);
  if (!response.ok) {
    const labels: Record<string,string> = {email:'邮箱',password:'密码',display_name:'昵称',timezone:'时区',name:'空间名称',title:'标题',start_at:'开始时间',end_at:'结束时间',due_at:'截止时间',description:'备注',version:'版本'};
    const details = data.error?.fields?.map((v: {field: string; message: string}) => `${labels[v.field] || v.field}：${v.message}`).join('；');
    throw new ApiError(response.status, details || data.error?.message || '操作未完成，请重试。');
  }
  return data as T;
}

export interface CalendarEvent {id:string;workspace_id:string;title:string;description:string;start_at:string;end_at:string;status:'active'|'cancelled';version:number;}
export interface Task {id:string;title:string;description:string;due_at:string|null;priority:'low'|'normal'|'high';status:'pending'|'in_progress'|'done'|'cancelled';event_id:string|null;version:number;}
export async function allItems<T>(path:string):Promise<T[]> {
  const values:T[]=[];
  for(let offset=0;;offset+=500){
    const page=await api<{items:T[];has_more:boolean}>(path+(path.includes('?')?'&':'?')+`limit=500&offset=${offset}`);
    values.push(...page.items);if(!page.has_more)return values;
  }
}
