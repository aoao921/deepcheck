import os
import json
import requests
import yaml
from dotenv import load_dotenv
from app.models.models import db, LLMRecord

# 加载环境变量
load_dotenv()

# 大模型配置
LLM_BASE_URL = os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1')
LLM_API_KEY = os.getenv('LLM_API_KEY')
LLM_MODEL = os.getenv('LLM_MODEL', 'gpt-4o-mini')
LLM_MODEL_LONG_TEXT = os.getenv('LLM_MODEL_LONG_TEXT', 'qwen-long')
LLM_TEMPERATURE = float(os.getenv('LLM_TEMPERATURE', 0.6))

def call_llm(system_prompt, user_prompt, history=None, temperature=None, long_text=False):
    """调用大模型API

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        history: 历史对话记录，格式为[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        temperature: 温度参数，控制随机性

    Returns:
        大模型返回的文本
    """
    # if not LLM_API_KEY:
    #     raise ValueError("LLM_API_KEY环境变量未设置")
    # model = LLM_MODEL_LONG_TEXT if long_text else LLM_MODEL
    model=LLM_MODEL
    # 构建消息列表
    messages = [{"role": "system", "content": system_prompt}]

    # 添加历史对话
    if history:
        messages.extend(history)

    # 添加当前用户提示
    messages.append({"role": "user", "content": user_prompt})

    # 设置温度参数
    temp = temperature if temperature is not None else LLM_TEMPERATURE

    # 构建请求数据
    data = {
        "model": model,
        "messages": messages,
        "temperature": temp
    }

    # 发送请求
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}"
    }

    response = requests.post(
         f"{LLM_BASE_URL}/chat/completions",
        # "http://localhost:11434/api/generate",
        headers=headers,
        json=data
    )

    # 检查响应
    if response.status_code != 200:
        raise Exception(f"API请求失败: {response.status_code} - {response.text}")

    # 解析响应
    result = response.json()
    print("11111111111111111111111111111111111")
    print(result)
    print(messages)

    # 记录请求和响应
    try:
        # 提取响应内容
        response_content = result["choices"][0]["message"]["content"]

        # 提取usage信息
        usage = result.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", None)
        completion_tokens = usage.get("completion_tokens", None)
        total_tokens = usage.get("total_tokens", None)

        # 提取缓存token信息
        cached_tokens = None
        if usage.get("prompt_tokens_details"):
            cached_tokens = usage["prompt_tokens_details"].get("cached_tokens", None)

        # 创建记录
        llm_record = LLMRecord(
            request_id=result.get("id"),
            model_name=result.get("model", model),
            request_messages=messages,
            response_content=response_content,
            response_full=result,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens
        )

        # 保存到数据库
        db.session.add(llm_record)
        db.session.commit()
    except Exception as e:
        print(f"记录LLM请求失败: {e}")
        # 记录失败不影响主流程，继续返回结果

    return result["choices"][0]["message"]["content"]

def parse_yaml_response(response_text):
    """解析YAML格式的大模型响应

    Args:
        response_text: 大模型返回的YAML文本

    Returns:
        解析后的Python对象
    """
    try:
        # 尝试提取YAML部分
        if '```yaml' in response_text:
            yaml_parts = response_text.split('```yaml')
            if len(yaml_parts) > 1:
                yaml_content = yaml_parts[1].split('```')[0].strip()
            else:
                yaml_content = response_text
        elif '```' in response_text:
            yaml_parts = response_text.split('```')
            if len(yaml_parts) > 1:
                yaml_content = yaml_parts[1].strip()
            else:
                yaml_content = response_text
        else:
            yaml_content = response_text

        # 解析YAML
        return yaml.safe_load(yaml_content)
    except Exception as e:
        print(f"YAML解析错误: {e}")
        print(f"原始响应: {response_text}")
        return None