"""Exercise the actual HTTP adapter contract with bounded fake provider responses."""
import io
import json
from urllib.error import HTTPError,URLError
from pydantic import SecretStr
import pytest
from lifeagent import model_client as module


def config():
    return module.ModelSettings(provider='deepseek',model='deepseek-flash',api_key=SecretStr('test-private-key'),consent=True)


class Response:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def read(self,size):return self.data[:size]


def test_real_adapter_payload_allowlisted_endpoint_and_text_only(monkeypatch):
    seen=[]
    class Opener:
        def open(self,req,timeout):
            seen.append((req,timeout))
            return Response(json.dumps({'choices':[{'message':{'content':'真实格式文本','reasoning_content':'private reasoning'}}]}).encode())
    monkeypatch.setattr(module.request,'build_opener',lambda *_:Opener())
    assert module.complete(config(),[{'role':'user','content':'hello'}])=='真实格式文本'
    req,timeout=seen[0];body=json.loads(req.data)
    assert req.full_url=='https://api.deepseek.com/chat/completions' and timeout==45
    assert req.get_header('Authorization')=='Bearer test-private-key'
    assert body['stream'] is False and 'tools' not in body and body['thinking']=={'type':'disabled'}
    cfg=config().model_copy(update={'provider':'qwen-cn','workspace':'abc123','model':'qwen4-max'})
    module.complete(cfg,[{'role':'user','content':'hello'}])
    assert seen[-1][0].full_url=='https://abc123.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions'
    assert module.NoRedirect().redirect_request(None,None,302,'',{},'https://attacker.example') is None


@pytest.mark.parametrize('status,expected',[(400,'MODEL_CONFIGURATION_ERROR'),(404,'MODEL_CONFIGURATION_ERROR'),(401,'MODEL_AUTH_FAILED'),(403,'MODEL_AUTH_FAILED'),(402,'MODEL_RATE_LIMITED'),(429,'MODEL_RATE_LIMITED'),(500,'MODEL_UNAVAILABLE'),(302,'MODEL_UNAVAILABLE')])
def test_http_errors_are_sanitized(monkeypatch,status,expected):
    class Opener:
        def open(self,*_,**kw):raise HTTPError('https://provider',status,'contains test-private-key',{},io.BytesIO(b'sensitive provider body'))
    monkeypatch.setattr(module.request,'build_opener',lambda *_:Opener())
    with pytest.raises(module.ModelFailure) as e:module.complete(config(),[])
    assert e.value.code==expected and 'test-private-key' not in str(e.value) and 'sensitive' not in str(e.value)


@pytest.mark.parametrize('data',[b'not json',b'{}',json.dumps({'choices':[{'message':{'content':None,'reasoning_content':'reasoning'}}]}).encode(),json.dumps({'choices':[{'message':{'content':'x','tool_calls':[{}]}}]}).encode(),b'x'*524289])
def test_invalid_or_tool_responses_do_not_execute(monkeypatch,data):
    class Opener:
        def open(self,*_,**kw):return Response(data)
    monkeypatch.setattr(module.request,'build_opener',lambda *_:Opener())
    with pytest.raises(module.ModelFailure) as e:module.complete(config(),[])
    assert e.value.code=='MODEL_INVALID_RESPONSE'


@pytest.mark.parametrize('error,expected',[(TimeoutError(),'MODEL_TIMEOUT'),(URLError(TimeoutError()),'MODEL_TIMEOUT'),(URLError('dns failure'),'MODEL_UNAVAILABLE')])
def test_transport_failures(monkeypatch,error,expected):
    class Opener:
        def open(self,*_,**kw):raise error
    monkeypatch.setattr(module.request,'build_opener',lambda *_:Opener())
    with pytest.raises(module.ModelFailure) as e:module.complete(config(),[])
    assert e.value.code==expected
