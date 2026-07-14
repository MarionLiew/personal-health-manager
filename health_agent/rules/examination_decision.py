from __future__ import annotations

from health_agent.constants import ActionLevel

QUESTIONS = (
    "当前临床问题是什么？",
    "已有检查是否已经回答？",
    "新检查会增加什么信息？",
    "结果是否会改变处理？",
    "是否存在近期可复用旧影像？",
    "能否先观察或复查？",
    "是否有超声、MRI或其他替代方案？",
    "是否涉及辐射？",
    "是否涉及造影剂？",
    "是否涉及假阳性和过度诊断？",
    "是否为侵入性检查？",
    "应由哪个科室最终决定？",
)


def incomplete_assessment(test_name: str) -> dict[str, object]:
    return {
        "test_name": test_name,
        "questions": list(QUESTIONS),
        "conclusion": "现有信息不足以判断检查必要性，应结合临床问题与医生意见。",
        "action_level": ActionLevel.B.value,
    }
