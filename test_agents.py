#!/usr/bin/env python3
import sys
import os
sys.path.append('/workspace')

# 设置环境变量
os.environ.setdefault('RUNNING_IN_DOCKER', 'false')

try:
    from src.agents import agent_manager
    
    print("=== 检查已注册的智能体 ===")
    print(f"已注册的智能体类数量: {len(agent_manager._classes)}")
    
    print("\n=== 智能体详细信息 ===")
    for class_name, agent_class in agent_manager._classes.items():
        print(f"- {class_name}: {agent_class}")
        
    print("\n=== 已创建的智能体实例 ===") 
    print(f"智能体实例数量: {len(agent_manager._instances)}")
    
    for agent_id, instance in agent_manager._instances.items():
        print(f"- {agent_id}: {instance.__class__.__name__}")
        
    print("\n=== 测试获取智能体信息 ===")
    import asyncio
    
    async def test_agent_info():
        try:
            agents_info = await agent_manager.get_agents_info()
            print(f"成功获取 {len(agents_info)} 个智能体信息:")
            for info in agents_info:
                print(f"  - ID: {info.get('id')}")
                print(f"    名称: {info.get('name')}")
                print(f"    描述: {info.get('description')}")
                print(f"    能力: {info.get('capabilities', [])}")
                print()
        except Exception as e:
            print(f"获取智能体信息失败: {e}")
            
    asyncio.run(test_agent_info())
    
except Exception as e:
    print(f"测试失败: {e}")
    import traceback
    traceback.print_exc()