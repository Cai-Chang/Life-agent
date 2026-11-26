"""Test-only API entry point: deterministic replies, never a real model service."""
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from lifeagent.main import create_app
from lifeagent.model_client import ModelFailure
import uvicorn

app=create_app()
attempts={}


def fixture_model(config,messages):
    if config.api_key.get_secret_value()!='test-only-model-key':
        raise ModelFailure('MODEL_AUTH_FAILED')
    question=messages[-1]['content']
    attempts[question]=attempts.get(question,0)+1
    if question=='请模拟一次限流' and attempts[question]==1:
        raise ModelFailure('MODEL_RATE_LIMITED')
    if question=='等待刷新恢复':
        time.sleep(2)
    prior=[m['content'] for m in messages[:-1] if m['role']=='user']
    return '测试模型回复：'+question+('\n此前用户消息：'+' / '.join(prior) if prior else '')


app.state.model_client=fixture_model
if __name__=='__main__':
    uvicorn.run(app,host='127.0.0.1',port=8765,access_log=False)
