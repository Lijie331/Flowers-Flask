"""
内容审核工具模块 - 阿里云内容安全新版SDK
"""

import json
import base64
import os
import uuid
from datetime import datetime
from config import ALIYUN_CONTENT_MODERATION, ENABLE_CONTENT_MODERATION

# 阿里云新版SDK
from alibabacloud_green20220302.client import Client
from alibabacloud_green20220302 import models
from alibabacloud_tea_openapi.models import Config

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ContentModerationClient:
    """阿里云内容审核客户端（新版SDK）"""

    def __init__(self):
        self.config = ALIYUN_CONTENT_MODERATION
        self.access_key_id = self.config['access_key_id']
        self.access_key_secret = self.config['access_key_secret']
        self.region = self.config.get('region', 'cn-shanghai')
        self.endpoint = self.config['endpoint']

        # 初始化阿里云客户端
        self.clt = Client(
            Config(
                access_key_id=self.access_key_id,
                access_key_secret=self.access_key_secret,
                region_id=self.region,
                endpoint=self.endpoint,
                connect_timeout=10000,
                read_timeout=30000,
            )
        )

    def moderate_content(self, content, images=None):
        """
        审核内容（文本+图片）

        Returns:
            dict: {
                'pass': bool,
                'risk_level': str,  # P0/P1/P2/none
                'labels': list,
                'max_score': float,
                'suggestion': str  # block/review/pass
            }
        """
        if not ENABLE_CONTENT_MODERATION:
            return {'pass': True, 'risk_level': 'none', 'labels': [], 'max_score': 0, 'suggestion': 'pass'}

        results = {
            'text': None,
            'images': [],
        }
        all_labels = []
        max_score = 0

        # 审核文本（使用智能体）
        if content:
            text_result = self._moderate_text(content)
            results['text'] = text_result
            all_labels.extend(text_result.get('labels', []))
            max_score = max(max_score, text_result.get('score', 0))

        # 审核图片（使用新版SDK的image_moderation）
        if images:
            image_list = images if isinstance(images, list) else [images]
            for img_path in image_list:
                img_result = self._moderate_image(img_path)
                results['images'].append(img_result)
                all_labels.extend(img_result.get('labels', []))
                max_score = max(max_score, img_result.get('score', 0))

        # 综合判定
        final_risk_level = self._determine_risk_level(all_labels, max_score)
        final_pass = final_risk_level == 'none'
        final_suggestion = self._labels_to_suggestion(final_risk_level)

        return {
            'pass': final_pass,
            'risk_level': final_risk_level,
            'labels': list(set(all_labels)),
            'max_score': max_score,
            'suggestion': final_suggestion,
            'details': results
        }

    def _moderate_text(self, text):
        """审核文本（使用新版SDK的text_moderation_plus）"""
        try:
            service_params = {
                'content': text,
                'DataId': str(uuid.uuid4())
            }

            request = models.TextModerationPlusRequest(
                service='comment_detection_pro',
                service_parameters=json.dumps(service_params)
            )

            print(f"[DEBUG] 发送文本审核请求: content_len={len(text)}")
            response = self.clt.text_moderation_plus(request)

            print(f"[DEBUG] 文本审核响应状态: {response.status_code}")

            if response.status_code == 200:
                return self._parse_text_response(response.body)
            else:
                return {
                    'pass': False,
                    'risk_level': 'P1',
                    'labels': ['api_error'],
                    'score': 50,
                    'suggestion': 'review',
                    'error': f'HTTP {response.status_code}'
                }

        except Exception as e:
            print(f"[ERROR] 文本审核失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'pass': False,
                'risk_level': 'P1',
                'labels': ['audit_error'],
                'score': 50,
                'suggestion': 'review',
                'error': str(e)
            }

    def _moderate_image(self, image_path):
        """审核图片（使用base64编码）"""
        try:
            # 转换路径
            if image_path.startswith('/static/'):
                actual_path = os.path.join(PROJECT_ROOT, image_path.lstrip('/'))
            else:
                actual_path = image_path

            print(f"[DEBUG] 图片路径: {image_path} -> {actual_path}, 存在: {os.path.exists(actual_path)}")

            if not os.path.exists(actual_path):
                return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}

            with open(actual_path, 'rb') as f:
                img_base64 = base64.b64encode(f.read()).decode('utf-8')

            service_params = {
                'images': [
                    {'dataId': str(uuid.uuid4()), 'data': img_base64}
                ]
            }

            request = models.ImageModerationRequest(
                service='image_moderation',
                service_parameters=json.dumps(service_params)
            )

            print(f"[DEBUG] 发送图片审核请求")
            response = self.clt.image_moderation(request)

            print(f"[DEBUG] 图片审核响应状态: {response.status_code}")

            if response.status_code == 200:
                return self._parse_image_response(response.body)
            else:
                return {
                    'pass': False,
                    'risk_level': 'P1',
                    'labels': ['api_error'],
                    'score': 50,
                    'suggestion': 'review',
                    'error': f'HTTP {response.status_code}'
                }

        except Exception as e:
            print(f"[ERROR] 图片审核失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'pass': False,
                'risk_level': 'P1',
                'labels': ['audit_error'],
                'score': 50,
                'suggestion': 'review',
                'error': str(e)
            }

    def _parse_text_response(self, body):
        """解析文本审核响应"""
        try:
            print(f"[DEBUG] 文本响应体: {body}")

            code = body.code
            msg = body.message or ''
            data = body.data

            if code != 200:
                return {
                    'pass': False,
                    'risk_level': 'P1',
                    'labels': ['api_error'],
                    'score': 50,
                    'suggestion': 'review',
                    'error': msg or f'Code: {code}'
                }

            # 解析结果
            labels = []
            max_confidence = 0
            risk_level_str = 'none'

            if data and hasattr(data, 'result') and data.result:
                for item in data.result:
                    label = getattr(item, 'label', '') or ''
                    confidence = float(getattr(item, 'confidence', 0) or 0)
                    if label:
                        labels.append(label)
                    if confidence > max_confidence:
                        max_confidence = confidence

            # RiskLevel映射
            risk_map = {
                'high': 'P0',
                'medium': 'P1',
                'low': 'P2',
                'none': 'none'
            }
            mapped_risk = risk_map.get(risk_level_str, 'none')
            suggestion = self._labels_to_suggestion(mapped_risk)

            return {
                'pass': mapped_risk == 'none',
                'risk_level': mapped_risk,
                'labels': labels,
                'score': max_confidence,
                'suggestion': suggestion
            }

        except Exception as e:
            print(f"[ERROR] 解析文本响应失败: {e}")
            return {
                'pass': False,
                'risk_level': 'P1',
                'labels': ['parse_error'],
                'score': 50,
                'suggestion': 'review',
                'error': str(e)
            }

    def _parse_image_response(self, body):
        """解析图片审核响应"""
        try:
            print(f"[DEBUG] 图片响应体类型: {type(body)}")
            print(f"[DEBUG] 图片响应体: code={body.code}, msg={body.msg}, data={body.data}")

            code = body.code
            msg = body.msg or ''
            data = body.data

            if code != 200:
                return {
                    'pass': False,
                    'risk_level': 'P1',
                    'labels': ['api_error'],
                    'score': 50,
                    'suggestion': 'review',
                    'error': msg or f'Code: {code}'
                }

            # 解析结果
            labels = []
            max_confidence = 0
            risk_level_str = getattr(data, 'risk_level', 'none') if data else 'none'

            if data and hasattr(data, 'result') and data.result:
                for item in data.result:
                    label = getattr(item, 'label', '') or ''
                    confidence = float(getattr(item, 'confidence', 0) or 0)
                    if label and label != 'nonLabel':
                        labels.append(label)
                    if confidence > max_confidence:
                        max_confidence = confidence

            # RiskLevel映射
            risk_map = {
                'high': 'P0',
                'medium': 'P1',
                'low': 'P2',
                'none': 'none'
            }
            mapped_risk = risk_map.get(risk_level_str, 'none')
            suggestion = self._labels_to_suggestion(mapped_risk)

            print(f"[INFO] 图片审核结果: labels={labels}, confidence={max_confidence}, risk={mapped_risk}")

            return {
                'pass': mapped_risk == 'none',
                'risk_level': mapped_risk,
                'labels': labels,
                'score': max_confidence,
                'suggestion': suggestion
            }

        except Exception as e:
            print(f"[ERROR] 解析图片响应失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'pass': False,
                'risk_level': 'P1',
                'labels': ['parse_error'],
                'score': 50,
                'suggestion': 'review',
                'error': str(e)
            }

    def _determine_risk_level(self, labels, score):
        """根据标签列表和分数确定最终风险等级"""
        config = ALIYUN_CONTENT_MODERATION
        p0_labels = config.get('P0_LABELS', [])
        p1_labels = config.get('P1_LABELS', [])
        p2_labels = config.get('P2_LABELS', [])
        thresholds = config.get('thresholds', {'P0': 60, 'P1': 50, 'P2': 30})

        p0_found = set(labels) & set(p0_labels)
        p1_found = set(labels) & set(p1_labels)
        p2_found = set(labels) & set(p2_labels)

        if p0_found:
            return 'P0'
        elif p1_found:
            return 'P1'
        elif p2_found:
            return 'P2'
        elif score >= thresholds['P0']:
            return 'P0'
        elif score >= thresholds['P1']:
            return 'P1'
        elif score >= thresholds['P2']:
            return 'P2'
        return 'none'

    def _labels_to_suggestion(self, risk_level):
        """根据风险等级确定建议"""
        if risk_level == 'P0':
            return 'block'
        elif risk_level == 'P1':
            return 'review'
        return 'pass'


# 全局客户端实例
_moderation_client = None


def get_moderation_client():
    """获取审核客户端单例"""
    global _moderation_client
    if _moderation_client is None:
        _moderation_client = ContentModerationClient()
    return _moderation_client


def moderate_post(content, images=None, video_url=None):
    """兼容旧接口的快捷审核函数"""
    client = get_moderation_client()
    result = client.moderate_content(content, images)
    # 适配旧接口返回值结构
    if video_url:
        result['video'] = {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}
    return result
