import os
import re
import asyncio
import aiohttp
from typing import Optional
from PIL import Image, ImageFilter

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

# xnxx_api 导入
try:
    from xnxx_api import Client
except ImportError:
    Client = None
    logger.warning("xnxx_api 未安装，请运行 pip install xnxx-api")

# 硬编码的URL前缀
XNXX_BASE_URL = "https://www.xnxx.com/video-"


@register("astrbot_plugin_xnxx", "YourName", "XNXX 视频信息查询插件", "1.0.0")
class XNXXPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.cache_dir = ""
        self.last_cache_files = []
        self.proxy_url = ""
        self.blur_level = 50

    async def initialize(self):
        """插件初始化"""
        # 获取配置
        config = self.context.get_config(umo="global")
        self.proxy_url = config.get("proxy_url", "")
        self.blur_level = config.get("blur_level", 50)
        
        # 使用规范的插件数据目录
        self.cache_dir = os.path.join(get_astrbot_data_path(), "plugin_data", "astrbot_plugin_xnxx", "cache")
        
        # 创建缓存目录
        os.makedirs(self.cache_dir, exist_ok=True)
        logger.info(f"XNXX插件初始化完成，缓存目录: {self.cache_dir}")

    async def terminate(self):
        """插件销毁时清理缓存"""
        await self._cleanup_cache()

    async def _cleanup_cache(self):
        """清理上一次的缓存文件"""
        for file_path in self.last_cache_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"已清理缓存文件: {file_path}")
            except Exception as e:
                logger.error(f"清理缓存文件失败 {file_path}: {e}")
        self.last_cache_files.clear()

    async def _download_image(self, url: str) -> Optional[str]:
        """下载图片并返回本地路径"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            proxy = self.proxy_url if self.proxy_url else None

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        content = await response.read()
                        # 生成文件名
                        filename = f"thumb_{hash(url)}.jpg"
                        filepath = os.path.join(self.cache_dir, filename)
                        
                        with open(filepath, "wb") as f:
                            f.write(content)
                        
                        self.last_cache_files.append(filepath)
                        return filepath
        except Exception as e:
            logger.error(f"下载图片失败 {url}: {e}")
        return None

    async def _apply_blur(self, image_path: str) -> str:
        """对图片应用模糊效果"""
        try:
            img = Image.open(image_path)
            
            # 根据模糊级别应用模糊
            if self.blur_level > 0:
                blur_radius = self.blur_level  # 0-10
                blurred_img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                
                # 保存处理后的图片
                blurred_path = image_path.replace(".jpg", "_blurred.jpg")
                blurred_img.save(blurred_path, "JPEG", quality=85)
                
                # 更新缓存文件列表
                if image_path in self.last_cache_files:
                    self.last_cache_files.remove(image_path)
                self.last_cache_files.append(blurred_path)
                
                return blurred_path
            return image_path
        except Exception as e:
            logger.error(f"应用模糊效果失败: {e}")
            return image_path

    async def _get_video_info(self, video_id: str) -> Optional[dict]:
        """获取视频信息"""
        if Client is None:
            return None

        try:
            # 构建完整URL
            url = f"{XNXX_BASE_URL}{video_id}"
            
            # 在线程池中运行同步的 xnxx_api
            loop = asyncio.get_event_loop()
            # 配置代理
            from base_api.modules.config import RuntimeConfig
            config = RuntimeConfig()
            if self.proxy_url:
                config.proxy = self.proxy_url
            client = Client(core=config)
            video = await loop.run_in_executor(None, client.get_video, url)
            
            info = {
                "title": video.title,
                "likes": video.likes,
                "dislikes": video.dislikes,
                "views": video.views,
                "length": video.length,
                "author": video.author,
                "highest_quality": video.highest_quality,
                "tags": video.tags,
                "pornstars": video.pornstars,
                "description": video.description,
                "thumbnail_url": video.thumbnail_url[0] if video.thumbnail_url else None,
                "publish_date": video.publish_date,
                "comment_count": video.comment_count
            }
            return info
        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            return None

    @filter.command("xnxx")
    async def xnxx_command(self, event: AstrMessageEvent):
        """查询XNXX视频信息，用法: /xnxx <视频ID>"""
        # 先清理上一次的缓存
        await self._cleanup_cache()

        # 获取视频ID
        message_parts = event.message_str.strip().split()
        if len(message_parts) < 2:
            yield event.plain_result("用法: /xnxx <视频ID>\u200E")
            return

        video_id = message_parts[1].strip()

        # 发送获取中消息
        yield event.plain_result("正在获取视频信息...\u200E")

        # 获取视频信息
        info = await self._get_video_info(video_id)
        if not info:
            yield event.plain_result("获取视频信息失败，请检查视频ID是否正确。\u200E")
            return

        # 构建信息文本
        info_text = f"""📹 标题: {info['title']}
👤 作者: {info['author']}
⏱️ 时长: {info['length']}分钟
👍 点赞: {info['likes']}
👎 点踩: {info['dislikes']}
👁️ 观看: {info['views']}
📅 发布: {info['publish_date']}
💬 评论: {info['comment_count']}
🎬 最高画质: {info['highest_quality']}
🏷️ 标签: {', '.join(info['tags'][:5])}{'...' if len(info['tags']) > 5 else ''}\u200E"""

        # 下载并处理缩略图
        thumbnail_path = None
        if info.get('thumbnail_url'):
            thumbnail_path = await self._download_image(info['thumbnail_url'])
            if thumbnail_path:
                thumbnail_path = await self._apply_blur(thumbnail_path)

        # 构建消息链
        chain = MessageChain().message(info_text)
        if thumbnail_path and os.path.exists(thumbnail_path):
            chain.image(thumbnail_path)

        yield event.chain_result(chain.chain)

    @filter.command("xnxx_search")
    async def xnxx_search_command(self, event: AstrMessageEvent):
        """搜索XNXX视频，用法: /xnxx_search <关键词>"""
        # 先清理上一次的缓存
        await self._cleanup_cache()

        message_parts = event.message_str.strip().split(maxsplit=1)
        if len(message_parts) < 2:
            yield event.plain_result("用法: /xnxx_search <关键词>\u200E")
            return

        query = message_parts[1].strip()

        yield event.plain_result(f"正在搜索: {query}...\u200E")

        if Client is None:
            yield event.plain_result("xnxx_api 未安装，无法使用搜索功能。\u200E")
            return

        try:
            loop = asyncio.get_event_loop()
            # 配置代理
            from base_api.modules.config import RuntimeConfig
            config = RuntimeConfig()
            if self.proxy_url:
                config.proxy = self.proxy_url
            client = Client(core=config)
            search = await loop.run_in_executor(None, client.search, query)
            
            # 获取前5个视频
            videos = []
            count = 0
            async for video in search.videos(pages=1):
                if count >= 5:
                    break
                videos.append(video)
                count += 1

            if not videos:
                yield event.plain_result("未找到相关视频。\u200E")
                return

            # 构建搜索结果
            result_text = f"🔍 搜索结果: {query}\n\n"
            for i, video in enumerate(videos, 1):
                result_text += f"{i}. {video.title}\n"
                result_text += f"   时长: {video.length} | 画质: {video.highest_quality}\n"
                # 提取视频ID
                video_id_match = re.search(r'/video-([a-z0-9]+)', video.url)
                if video_id_match:
                    result_text += f"   ID: {video_id_match.group(1)}\n"
                result_text += "\n"

            yield event.plain_result(f"{result_text}\u200E")

        except Exception as e:
            logger.error(f"搜索失败: {e}")
            yield event.plain_result(f"搜索失败: {str(e)}\u200E")

    @filter.command("xnxx_user")
    async def xnxx_user_command(self, event: AstrMessageEvent):
        """获取用户信息，用法: /xnxx_user <用户URL或ID>"""
        # 先清理上一次的缓存
        await self._cleanup_cache()

        message_parts = event.message_str.strip().split(maxsplit=1)
        if len(message_parts) < 2:
            yield event.plain_result("用法: /xnxx_user <用户URL>\u200E")
            return

        user_input = message_parts[1].strip()

        yield event.plain_result("正在获取用户信息...\u200E")

        if Client is None:
            yield event.plain_result("xnxx_api 未安装，无法使用此功能。\u200E")
            return

        try:
            # 如果输入的是ID，构建完整URL
            if not user_input.startswith("http"):
                user_url = f"https://www.xnxx.com/pornstars/{user_input}"
            else:
                user_url = user_input

            loop = asyncio.get_event_loop()
            # 配置代理
            from base_api.modules.config import RuntimeConfig
            config = RuntimeConfig()
            if self.proxy_url:
                config.proxy = self.proxy_url
            client = Client(core=config)
            user = await loop.run_in_executor(None, client.get_user, user_url)

            user_text = f"""👤 用户信息
📛 名称: {user_input}
🎬 视频总数: {user.total_videos}
👁️ 总观看量: {user.total_video_views}
📄 总页数: {user.total_pages}\u200E"""

            yield event.plain_result(user_text)

        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            yield event.plain_result(f"获取用户信息失败: {str(e)}\u200E")
