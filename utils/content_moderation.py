"""
内容审核工具模块 - 封装阿里云通义千问内容审核API
"""

import json
import base64
import os
from datetime import datetime
from config import ALIYUN_CONTENT_MODERATION, ENABLE_CONTENT_MODERATION

# 阿里云SDK
from aliyunsdkcore import client
from aliyunsdkcore.request import CommonRequest
from aliyunsdkgreen.request.v20180509 import TextScanRequest, ImageSyncScanRequest

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ContentModerationClient:
    """阿里云内容审核客户端"""

    def __init__(self):
        self.config = ALIYUN_CONTENT_MODERATION
        self.access_key_id = self.config['access_key_id']
        self.access_key_secret = self.config['access_key_secret']
        self.region = self.config.get('region', 'cn-shanghai')
        self.thresholds = self.config['thresholds']
        self.p0_labels = self.config['P0_LABELS']
        self.p1_labels = self.config['P1_LABELS']
        self.p2_labels = self.config['P2_LABELS']

        # 初始化阿里云客户端
        self.clt = client.AcsClient(
            self.access_key_id,
            self.access_key_secret,
            self.region
        )

    def _call_text_api(self, body):
        """调用文本审核API"""
        request = TextScanRequest.TextScanRequest()
        request.set_accept_format('json')
        request.set_content(bytearray(json.dumps(body), 'utf-8'))
        response = self.clt.do_action(request)
        return json.loads(response.decode('utf-8'))

    def _call_image_api(self, body):
        """调用图片审核API"""
        request = ImageSyncScanRequest.ImageSyncScanRequest()
        request.set_accept_format('json')
        request.set_content(bytearray(json.dumps(body), 'utf-8'))
        response = self.clt.do_action(request)
        return json.loads(response.decode('utf-8'))

    def _call_video_api(self, body):
        """调用视频审核API"""
        request = CommonRequest()
        request.set_accept_format('json')
        request.set_domain('green.cn-shanghai.aliyuncs.com')
        request.set_method('POST')
        request.set_protocol_type('https')
        request.set_version('2018-05-09')
        request.set_action_name('VideoAsyncScan')
        request.set_content(bytearray(json.dumps(body), 'utf-8'))
        response = self.clt.do_action(request)
        return json.loads(response.decode('utf-8'))

    def moderate_text(self, text):
        """
        审核文本内容

        Returns:
            dict: {
                'pass': bool,
                'risk_level': str,  # P0/P1/P2/none
                'labels': list,
                'score': float,
                'suggestion': str  # block/review/pass
            }
        """
        if not ENABLE_CONTENT_MODERATION:
            return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}

        try:
            body = {
                'text': text,
                'bizType': 'post_content'
            }

            result = self._call_text_api(body)
            print(f"[INFO] 文本审核API返回: {result}")

            # 检查API是否返回错误
            if result.get('Code') or result.get('Message'):
                print(f"[WARN] API返回错误: {result}")
                return {
                    'pass': False,
                    'risk_level': 'P1',
                    'labels': ['api_error'],
                    'score': 50,
                    'suggestion': 'review',
                    'error': result.get('Message', 'Unknown error')
                }

            return self._parse_text_response(result)

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

    def moderate_image(self, image_path=None, image_url=None, image_base64=None):
        """
        审核图片内容
        """
        if not ENABLE_CONTENT_MODERATION:
            return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}

        try:
            images_data = []
            actual_file_path = None

            if image_path:
                # 如果是相对路径（/static/...），转换成实际文件路径
                if image_path.startswith('/static/'):
                    actual_file_path = os.path.join(PROJECT_ROOT, image_path.lstrip('/'))
                else:
                    actual_file_path = image_path
                print(f"[DEBUG] 图片路径: {image_path} -> {actual_file_path}, 存在: {os.path.exists(actual_file_path)}")
                with open(actual_file_path, 'rb') as f:
                    img_base64 = base64.b64encode(f.read()).decode('utf-8')
                images_data.append({'dataId': 'img1', 'data': img_base64})
            elif image_url:
                # 如果是相对路径，转换成实际文件路径
                if image_url.startswith('/static/'):
                    actual_file_path = os.path.join(PROJECT_ROOT, image_url.lstrip('/'))
                    print(f"[DEBUG] 图片URL: {image_url} -> {actual_file_path}, 存在: {os.path.exists(actual_file_path)}")
                    if os.path.exists(actual_file_path):
                        with open(actual_file_path, 'rb') as f:
                            img_base64 = base64.b64encode(f.read()).decode('utf-8')
                        images_data.append({'dataId': 'img1', 'data': img_base64})
                    else:
                        print(f"[WARN] 图片文件不存在: {actual_file_path}")
                        return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}
                else:
                    images_data.append({'dataId': 'img1', 'url': image_url})
            elif image_base64:
                images_data.append({'dataId': 'img1', 'data': image_base64})
            else:
                return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}

            body = {
                'images': images_data,
                'bizType': 'post_content'
            }

            print(f"[DEBUG] 发送图片审核请求，图片数量: {len(images_data)}")
            result = self._call_image_api(body)
            print(f"[INFO] 图片审核API返回: {result}")

            # 检查API是否返回错误
            if result.get('Code') or result.get('Message'):
                print(f"[WARN] API返回错误: {result}")
                return {
                    'pass': False,
                    'risk_level': 'P1',
                    'labels': ['api_error'],
                    'score': 50,
                    'suggestion': 'review',
                    'error': result.get('Message', 'Unknown error')
                }

            return self._parse_image_response(result)

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

    def moderate_video(self, video_url):
        """
        审核视频内容（异步方式）
        """
        if not ENABLE_CONTENT_MODERATION:
            return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}

        try:
            body = {
                'videoUrl': video_url,
                'bizType': 'post_content'
            }

            result = self._call_video_api(body)
            print(f"[INFO] 视频审核API返回: {result}")
            return self._parse_video_response(result)

        except Exception as e:
            print(f"[ERROR] 视频审核失败: {e}")
            return {
                'pass': False,
                'risk_level': 'P1',
                'labels': ['audit_error'],
                'score': 50,
                'suggestion': 'review',
                'error': str(e)
            }

    def moderate_content(self, content, images=None, video_url=None):
        """
        综合审核帖子内容（文本+图片+视频）
        """
        print(f"[DEBUG] moderate_content called - content: {content[:50] if content else None}, images: {images}, video_url: {video_url}")

        results = {
            'text': None,
            'images': [],
            'video': None
        }
        all_labels = []
        max_score = 0

        # 审核文本
        if content:
            text_result = self.moderate_text(content)
            results['text'] = text_result
            all_labels.extend(text_result.get('labels', []))
            max_score = max(max_score, text_result.get('score', 0))

        # 审核图片
        print(f"[DEBUG] images type: {type(images)}, value: {images}")
        if images:
            for img in images:
                print(f"[DEBUG] processing image: {img}, type: {type(img)}")
                if isinstance(img, str):
                    if img.startswith('http'):
                        img_result = self.moderate_image(image_url=img)
                    else:
                        img_result = self.moderate_image(image_path=img)
                else:
                    img_result = self.moderate_image(image_base64=img)

                results['images'].append(img_result)
                all_labels.extend(img_result.get('labels', []))
                max_score = max(max_score, img_result.get('score', 0))

        # 审核视频
        if video_url:
            video_result = self.moderate_video(video_url)
            results['video'] = video_result
            all_labels.extend(video_result.get('labels', []))
            max_score = max(max_score, video_result.get('score', 0))

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

    def _parse_text_response(self, response):
        """解析文本审核API响应"""
        try:
            # 阿里云文本审核返回格式
            # {"code": 200, "data": [{"scene": "antispam", "label": "normal", "score": 0.0, "suggestion": "pass"}]}
            if response.get('code') == 200 and response.get('data'):
                for item in response['data']:
                    label = item.get('label', 'normal')
                    score = float(item.get('score', 0))
                    suggestion = item.get('suggestion', 'pass')

                    risk_level = self._label_to_risk_level(label, score)

                    return {
                        'pass': suggestion == 'pass',
                        'risk_level': risk_level,
                        'labels': [label] if label != 'normal' else [],
                        'score': score,
                        'suggestion': suggestion
                    }
            return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}
        except Exception as e:
            print(f"[ERROR] 解析文本响应失败: {e}")
            return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}

    def _parse_image_response(self, response):
        """解析图片审核API响应"""
        try:
            if response.get('code') == 200 and response.get('data'):
                for item in response['data']:
                    label = item.get('label', 'normal')
                    score = float(item.get('score', 0))
                    suggestion = item.get('suggestion', 'pass')

                    risk_level = self._label_to_risk_level(label, score)

                    return {
                        'pass': suggestion == 'pass',
                        'risk_level': risk_level,
                        'labels': [label] if label != 'normal' else [],
                        'score': score,
                        'suggestion': suggestion
                    }
            return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}
        except Exception as e:
            print(f"[ERROR] 解析图片响应失败: {e}")
            return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}

    def _parse_video_response(self, response):
        """解析视频审核API响应"""
        try:
            if response.get('code') == 200 and response.get('data'):
                data = response['data']
                label = data.get('label', 'normal')
                score = float(data.get('score', 0))

                risk_level = self._label_to_risk_level(label, score)

                return {
                    'pass': risk_level == 'none',
                    'risk_level': risk_level,
                    'labels': [label] if label != 'normal' else [],
                    'score': score,
                    'suggestion': 'block' if risk_level == 'P0' else ('review' if risk_level == 'P1' else 'pass')
                }
            return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}
        except Exception as e:
            print(f"[ERROR] 解析视频响应失败: {e}")
            return {'pass': True, 'risk_level': 'none', 'labels': [], 'score': 0, 'suggestion': 'pass'}

    def _label_to_risk_level(self, label, score):
        """根据标签和分数判定风险等级"""
        if label in self.p0_labels:
            return 'P0'
        if label in self.p1_labels:
            return 'P1'
        if label in self.p2_labels:
            return 'P2'
        if score >= self.thresholds['P0']:
            return 'P0'
        if score >= self.thresholds['P1']:
            return 'P1'
        if score >= self.thresholds['P2']:
            return 'P2'
        return 'none'

    def _determine_risk_level(self, labels, score):
        """根据标签列表和分数确定最终风险等级"""
        p0_found = set(labels) & set(self.p0_labels)
        p1_found = set(labels) & set(self.p1_labels)
        p2_found = set(labels) & set(self.p2_labels)

        if p0_found:
            return 'P0'
        elif p1_found:
            return 'P1'
        elif p2_found:
            return 'P2'
        elif score >= self.thresholds['P0']:
            return 'P0'
        elif score >= self.thresholds['P1']:
            return 'P1'
        elif score >= self.thresholds['P2']:
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
    """
    快捷审核函数
    """
    client = get_moderation_client()
    return client.moderate_content(content, images, video_url)