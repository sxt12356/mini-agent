from fastapi import Depends, Request

from mini_agent.agent.schemas import UserContext
from mini_agent.core.auth import CurrentUser, get_current_user
from mini_agent.core.rate_limit import check_chat_rate_limit


def build_user_context(current_user: CurrentUser) -> UserContext:
    return UserContext(
        user_id=current_user.user_id,
        role=current_user.role,
    )


async def get_rate_limited_current_user(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    result = await check_chat_rate_limit(
        request=request,
        current_user=current_user,
    )

    request.state.chat_rate_limit = result

    return current_user