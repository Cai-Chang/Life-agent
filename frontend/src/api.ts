export interface Workspace { id: string; name: string; type: 'personal'; role: 'owner'; created_at: string; }
export interface Profile { user: {id: string; email: string; display_name: string; timezone: string; created_at: string}; workspace: Workspace; csrf_token: string; }
export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
let csrf = '';
export function setSession(profile: Profile | null) { csrf = profile?.csrf_token || ''; }

export async function api<T>(path: string, body?: unknown, method?: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch('/api/v1' + path, {credentials: 'same-origin', cache: 'no-store',
      method: method || (body === undefined ? 'GET' : 'POST'),
      headers: body === undefined ? {} : {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal: AbortSignal.timeout(15000)});
  } catch { throw new ApiError(0, '暂时连接不上服务，请检查网络后重试。'); }
  if (response.status === 204) return undefined as T;
  let data;
  try { data = await response.json(); } catch { throw new ApiError(response.status, '服务暂不可用，请稍后重试。'); }
  if (!response.ok) {
    const labels: Record<string,string> = {email:'邮箱',password:'密码',display_name:'昵称',timezone:'时区',name:'空间名称'};
    const details = data.error?.fields?.map((v: {field: string; message: string}) => `${labels[v.field] || v.field}：${v.message}`).join('；');
    throw new ApiError(response.status, details || data.error?.message || '操作未完成，请重试。');
  }
  return data as T;
}
