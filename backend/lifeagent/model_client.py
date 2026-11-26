"""Bounded OpenAI-compatible calls. Credentials stay server-side in private files."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import tempfile
from urllib import request, error
from uuid import UUID

from pydantic import Field, SecretStr, field_validator
from typing import Literal
from lifeagent.auth import Input, problem

PROVIDERS = {
    'deepseek': {'label':'DeepSeek', 'default_model':'deepseek-flash', 'endpoint':'https://api.deepseek.com/chat/completions'},
    'qwen-cn': {'label':'通义千问 · 北京', 'default_model':'qwen4-max', 'endpoint':'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'},
    'qwen-intl': {'label':'通义千问 · 新加坡', 'default_model':'qwen4-max', 'endpoint':'https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions'},
}
ERRORS = {
    'MODEL_CONFIGURATION_ERROR':'模型服务不接受当前配置，请检查模型名称、服务商与地域。',
    'MODEL_AUTH_FAILED':'模型服务鉴权失败，请检查该服务和地域对应的 API Key。',
    'MODEL_RATE_LIMITED':'模型服务限流或额度不足，请稍后再试并检查服务商额度。',
    'MODEL_TIMEOUT':'模型响应超时，本次未收到完整回复，可以手动重试。',
    'MODEL_UNAVAILABLE':'暂时无法连接模型服务，请稍后重试。',
    'MODEL_INVALID_RESPONSE':'模型没有返回有效文本，请检查模型名称或重试。',
    'MODEL_INTERRUPTED':'上次回复未完成，可以手动重试。',
}


class ModelFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(ERRORS.get(code, ERRORS['MODEL_UNAVAILABLE']))


class ModelSettings(Input):
    provider: Literal['deepseek', 'qwen-cn', 'qwen-intl']
    model: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9._:/-]*$')
    api_key: SecretStr | None = None
    workspace: str = Field(default='', max_length=128, pattern=r'^[A-Za-z0-9_-]*$')
    consent: Literal[True]

    @field_validator('api_key')
    @classmethod
    def valid_key(cls, value):
        if value is not None:
            raw = value.get_secret_value().strip()
            if not 1 <= len(raw) <= 512 or not raw.isascii() or not all(33 <= ord(c) <= 126 for c in raw):
                raise ValueError('请输入有效的 API Key')
            return SecretStr(raw)
        return value


def config_path(user_id):
    root = Path(os.environ.get('LIFEAGENT_MODEL_CONFIG_DIR', Path(__file__).resolve().parents[2]/'.local/model-settings'))
    return root / (str(UUID(str(user_id)))+'.json')


def read_config(user_id):
    path = config_path(user_id)
    try:
        if path.stat().st_mode & 0o077:
            raise problem(503, 'MODEL_STORAGE_UNAVAILABLE', '模型配置文件权限异常，请联系管理员检查。')
        with path.open() as stream:
            value = ModelSettings.model_validate(json.load(stream))
        if value.api_key is None:
            raise ValueError('missing key')
        return value
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise problem(503, 'MODEL_STORAGE_UNAVAILABLE', '暂时无法读取模型配置，请重新保存配置。') from None


def public_settings(user_id):
    value = read_config(user_id)
    return {'configured':value is not None, 'provider':value.provider if value else 'deepseek',
        'model':value.model if value else PROVIDERS['deepseek']['default_model'],
        'workspace':value.workspace if value else '', 'consent':bool(value and value.consent),
        'providers':[{'id':k,'label':v['label'],'default_model':v['default_model']} for k,v in PROVIDERS.items()]}


def save_config(user_id, value):
    if value.api_key is None:
        previous = read_config(user_id)
        if previous is None or previous.provider != value.provider or previous.workspace != value.workspace:
            raise problem(422, 'MODEL_KEY_REQUIRED', '首次配置或切换服务/地域时，请填写对应的 API Key。')
        value = value.model_copy(update={'api_key':previous.api_key})
    path = config_path(user_id)
    temporary = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        data = value.model_dump(mode='json', exclude={'api_key'})
        data['api_key'] = value.api_key.get_secret_value()
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        raise problem(503, 'MODEL_STORAGE_UNAVAILABLE', '无法保存模型配置，请检查服务配置目录。') from None
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return public_settings(user_id)


def remove_config(user_id):
    try:
        config_path(user_id).unlink(missing_ok=True)
    except OSError:
        raise problem(503, 'MODEL_STORAGE_UNAVAILABLE', '暂时无法删除模型配置，请稍后重试。') from None


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def complete(config, messages):
    endpoint = PROVIDERS[config.provider]['endpoint']
    if config.workspace and config.provider != 'deepseek':
        region = 'cn-beijing' if config.provider == 'qwen-cn' else 'ap-southeast-1'
        endpoint = f'https://{config.workspace}.{region}.maas.aliyuncs.com/compatible-mode/v1/chat/completions'
    body = {'model':config.model, 'messages':messages, 'stream':False, 'max_tokens':1024}
    if config.provider == 'deepseek':
        body['thinking'] = {'type':'disabled'}
    else:
        body['enable_thinking'] = False
    req = request.Request(endpoint, data=json.dumps(body).encode(), method='POST',
        headers={'Content-Type':'application/json', 'Authorization':'Bearer '+config.api_key.get_secret_value()})
    try:
        with request.build_opener(NoRedirect()).open(req, timeout=45) as response:
            raw = response.read(524289)
            if len(raw) > 524288:
                raise ModelFailure('MODEL_INVALID_RESPONSE')
            data = json.loads(raw)
        message = data['choices'][0]['message']
        text = message.get('content')
        if message.get('tool_calls') or message.get('function_call') or not isinstance(text, str) or not text.strip() or len(text) > 16000:
            raise ModelFailure('MODEL_INVALID_RESPONSE')
        return text.strip()
    except error.HTTPError as exc:
        exc.close()
        code = 'MODEL_AUTH_FAILED' if exc.code in (401,403) else 'MODEL_RATE_LIMITED' if exc.code in (402,429) else 'MODEL_CONFIGURATION_ERROR' if exc.code in (400,404,422) else 'MODEL_UNAVAILABLE'
        raise ModelFailure(code) from None
    except (TimeoutError, socket.timeout):
        raise ModelFailure('MODEL_TIMEOUT') from None
    except error.URLError as exc:
        raise ModelFailure('MODEL_TIMEOUT' if isinstance(exc.reason, (TimeoutError,socket.timeout)) else 'MODEL_UNAVAILABLE') from None
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        raise ModelFailure('MODEL_INVALID_RESPONSE') from None
