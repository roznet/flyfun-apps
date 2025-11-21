#!/usr/bin/env python3
"""
Manual testing script for streaming endpoint.

Usage:
    python test_streaming_manual.py

Or test specific query:
    python test_streaming_manual.py "Find airports from EGTF to LFMD"
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from langchain_core.messages import HumanMessage
from shared.aviation_agent.adapters import build_agent, stream_aviation_agent
from shared.aviation_agent.config import AviationAgentSettings, get_settings


async def test_streaming(query: str = "Find airports from EGTF to LFMD"):
    """Test streaming with a query."""
    print(f"🧪 Testing streaming with query: {query}\n")
    
    # Get settings
    settings = get_settings()
    if not settings.enabled:
        print("❌ Aviation agent is disabled. Set AVIATION_AGENT_ENABLED=1")
        return
    
    # Build agent
    print("🔧 Building agent...")
    graph = build_agent(settings=settings)
    
    # Create messages
    messages = [HumanMessage(content=query)]
    
    # Stream events
    print("📡 Streaming events...\n")
    print("=" * 60)
    
    events_received = []
    async for event in stream_aviation_agent(messages, graph, session_id="test-session"):
        event_type = event.get("event")
        events_received.append(event_type)
        
        if event_type == "plan":
            print(f"✅ {event_type.upper()}:")
            data = event.get("data", {})
            print(f"   Tool: {data.get('selected_tool')}")
            print(f"   Arguments: {json.dumps(data.get('arguments', {}), indent=2)}")
            print()
        
        elif event_type == "thinking":
            print(f"💭 {event_type.upper()}:")
            content = event.get("data", {}).get("content", "")
            print(f"   {content[:100]}..." if len(content) > 100 else f"   {content}")
            print()
        
        elif event_type == "tool_call_start":
            print(f"🔧 {event_type.upper()}:")
            data = event.get("data", {})
            print(f"   Tool: {data.get('name')}")
            print()
        
        elif event_type == "tool_call_end":
            print(f"✅ {event_type.upper()}:")
            data = event.get("data", {})
            print(f"   Tool: {data.get('name')}")
            result = data.get("result", {})
            if "airports" in result:
                print(f"   Found {len(result.get('airports', []))} airports")
            print()
        
        elif event_type == "message":
            # Print message chunks inline
            content = event.get("data", {}).get("content", "")
            print(content, end="", flush=True)
        
        elif event_type == "thinking_done":
            print(f"\n\n✅ {event_type.upper()}\n")
        
        elif event_type == "ui_payload":
            print(f"\n✅ {event_type.upper()}:")
            data = event.get("data", {})
            print(f"   Kind: {data.get('kind')}")
            if "visualization" in data:
                print(f"   Has visualization: Yes")
            if "airports" in data:
                print(f"   Airports: {len(data.get('airports', []))}")
            print()
        
        elif event_type == "done":
            print(f"✅ {event_type.upper()}:")
            data = event.get("data", {})
            tokens = data.get("tokens", {})
            print(f"   Session ID: {data.get('session_id')}")
            print(f"   Tokens - Input: {tokens.get('input')}, Output: {tokens.get('output')}, Total: {tokens.get('total')}")
            print()
        
        elif event_type == "error":
            print(f"\n❌ {event_type.upper()}:")
            data = event.get("data", {})
            print(f"   {data.get('message')}")
            print()
    
    print("=" * 60)
    print(f"\n📊 Summary:")
    print(f"   Events received: {len(events_received)}")
    print(f"   Event types: {', '.join(set(events_received))}")
    
    # Verify expected events
    expected_events = ["plan", "tool_call_start", "tool_call_end", "message", "done"]
    missing = [e for e in expected_events if e not in events_received]
    if missing:
        print(f"   ⚠️  Missing events: {', '.join(missing)}")
    else:
        print(f"   ✅ All expected events received")


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "Find airports from EGTF to LFMD"
    asyncio.run(test_streaming(query))

