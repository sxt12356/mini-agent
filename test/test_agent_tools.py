from mini_agent.agent.tools import TOOL_POLICIES, TOOLS


def test_agent_tool_schemas_are_registered():
    tool_names = {tool["name"] for tool in TOOLS}

    assert tool_names == {
        "get_order_status",
        "cancel_order",
        "create_refund_ticket",
        "search_policy_knowledge_base",
    }
    assert tool_names == set(TOOL_POLICIES)

