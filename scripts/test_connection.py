"""
Quick connection tester for Codex Antigravity Bridge
Tests local gateway connectivity and model response.
"""

import sys
import asyncio
from google.antigravity import Agent, LocalOpenAIAgentConfig

async def test():
    print("🤖 正在测试本地 Antigravity 模型网关连接 (http://127.0.0.1:10100/v1)...")
    config = LocalOpenAIAgentConfig(
        base_url="http://127.0.0.1:10100/v1",
        model="agentrouter/glm-5.3",
        system_instructions="你是一个测试智能体。请只回复一行简单的问候语。"
    )
    try:
        chunks = []
        async with Agent(config) as agent:
            resp = await agent.chat("你好，请做简单回复。")
            async for token in resp:
                chunks.append(token)
        print("✔ 网关响应成功！模型输出：")
        print("".join(chunks).strip())
        print("\n🎉 环境测试通过！")
    except Exception as e:
        print(f"❌ 连接异常: {e}")

if __name__ == "__main__":
    asyncio.run(test())
