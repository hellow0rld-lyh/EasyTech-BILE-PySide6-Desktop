"""项目统一的防御性 XML 解析入口。

该模块只替代通用 XML 解码，不改变 EZ-Tech 图集的 XML 声明、多顶层片段或控制字节兼容策略；
调用方必须先完成其格式特有的、仅内存生效的清理，再调用本模块。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Final

from defusedxml.ElementTree import fromstring as safe_fromstring
from defusedxml.common import DefusedXmlException


XML_SECURITY_CONTRACT: Final = "拒绝 DTD、实体声明和外部引用；不执行 XML 包含、网络访问或文件引用。"


class SafeXmlError(ValueError):
    """XML 语法无效，或违反项目的安全解析合同。"""


def parse_untrusted_xml(text: str, source_name: str) -> ET.Element:
    """使用 defusedxml 解析文本，并将库异常收敛为项目稳定异常类型。"""
    try:
        return safe_fromstring(
            text,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except (DefusedXmlException, ET.ParseError) as exc:
        raise SafeXmlError(f"XML 无法安全解析（{source_name}）：{exc}") from exc
