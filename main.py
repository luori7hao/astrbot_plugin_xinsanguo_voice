import os
import json
import random
import re
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig, logger
from astrbot.api.star import StarTools
import astrbot.api.message_components as Comp

# 默认 LLM 唤醒词列表（模块级常量）
DEFAULT_LLM_PATTERNS = [
    r'[?？]',
    r'怎么',
    r'如何',
    r'为什么',
    r'什么是',
    r'是什么',
    r'能不能',
    r'可不可以',
    r'帮我',
    r'请问',
    r'告诉我',
    r'解释',
    r'说说',
    r'介绍',
    r'推荐',
    r'建议',
    r'分析',
    r'总结',
    r'翻译',
    r'写一',
    r'帮忙',
    r'教我',
    r'怎样',
    r'哪个',
    r'哪些',
    r'多少',
    r'几个',
    r'有没有',
    r'是否',
    r'能否',
    r'可以吗',
    r'行吗',
    r'好吗',
    r'对吗',
    r'吗$',
]

@register("astrbot_plugin_xinsanguo_voice", "落日七号、复读机长", "新三国自动玩梗语音插件 - 识别聊天中的新三国经典台词关键词，自动发送对应语音", "1.0.0", "https://github.com/luori7hao/astrbot_plugin_xinsanguo_voice")
class SanGuoMeme(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 路径设置：音频文件在插件目录下的 data/sound（只读）
        self.base_dir = os.path.dirname(__file__)
        self.audio_dir = os.path.join(self.base_dir, "data", "sound")
        
        # 使用 StarTools 获取持久化数据目录
        self.data_dir = StarTools.get_data_dir("xinsanguo_voice")
        self.rules_path = os.path.join(self.data_dir, "rules.json")
        
        # 如果持久化目录中没有 rules.json，从插件目录复制
        self._init_rules_file()
        
        # 预加载 rules.json
        self.rules = self._load_rules()
        
        # 统计信息
        self.trigger_count = 0
        
        # 从配置加载 LLM 唤醒词列表
        self.need_llm_patterns = self.config.get("llm_wake_patterns", DEFAULT_LLM_PATTERNS)
        
        # 从配置加载其他设置
        self.keyword_ratio_threshold = self.config.get("keyword_ratio_threshold", 0.5)
        self.wake_word_prefix = self.config.get("wake_word_prefix", "/")
        self.enable_group_only = self.config.get("enable_group_only", True)
        self.random_select = self.config.get("random_select", True)
        self.private_chat_llm_mode = self.config.get("private_chat_llm_mode", "smart")
        
        logger.info(f"[新三国语音] 插件初始化完成！已加载 {len(self.rules)} 条台词规则。")
        logger.info(f"[新三国语音] 音频目录: {self.audio_dir}")
        logger.info(f"[新三国语音] 数据目录: {self.data_dir}")
        logger.info(f"[新三国语音] LLM 唤醒词数量: {len(self.need_llm_patterns)}")

    def _init_rules_file(self):
        """初始化规则文件：如果持久化目录中没有，则从插件目录复制"""
        if os.path.exists(self.rules_path):
            return
        
        # 尝试从插件目录复制
        source_rules = os.path.join(self.base_dir, "rules.json")
        if os.path.exists(source_rules):
            try:
                with open(source_rules, 'r', encoding='utf-8') as f:
                    rules = json.load(f)
                with open(self.rules_path, 'w', encoding='utf-8') as f:
                    json.dump(rules, f, ensure_ascii=False, indent=4)
                logger.info(f"[新三国语音] 已从插件目录复制 rules.json 到数据目录")
            except Exception as e:
                logger.error(f"[新三国语音] 复制 rules.json 失败: {e}")
                self._create_default_rules()
        else:
            self._create_default_rules()

    def _load_rules(self) -> list:
        """加载关键词规则配置"""
        if not os.path.exists(self.rules_path):
            logger.warning(f"[新三国语音] 警告：找不到 rules.json，将创建默认配置")
            self._create_default_rules()
            return []
        try:
            with open(self.rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
                logger.info(f"[新三国语音] 成功加载 {len(rules)} 条规则")
                return rules
        except Exception as e:
            logger.error(f"[新三国语音] 读取 rules.json 失败: {e}")
            return []

    def _create_default_rules(self):
        """创建默认规则文件"""
        default_rules = [
            {"keyword": "不可能", "audio": "不可能，绝对不可能.mp3"},
            {"keyword": "愤怒", "audio": "不要愤怒，愤怒会降低你的智慧.mp3"},
            {"keyword": "龙", "audio": "龙，可是帝王之征啊.mp3"}
        ]
        try:
            with open(self.rules_path, 'w', encoding='utf-8') as f:
                json.dump(default_rules, f, ensure_ascii=False, indent=4)
            logger.info("[新三国语音] 已创建默认规则文件")
        except Exception as e:
            logger.error(f"[新三国语音] 创建默认规则文件失败: {e}")

    def _get_audio_path(self, rule: dict) -> str:
        """获取音频文件的完整路径"""
        rel_path = rule.get("audio", "")
        file_name = rel_path.replace("\\", "/").split("/")[-1]
        return os.path.join(self.audio_dir, file_name)

    def _match_keywords(self, message: str) -> list:
        """匹配消息中的关键词，返回匹配到的音频路径列表"""
        matched_audios = []
        for rule in self.rules:
            keyword = rule.get("keyword", "")
            if keyword and keyword in message:
                audio_path = self._get_audio_path(rule)
                if os.path.exists(audio_path):
                    matched_audios.append({
                        "keyword": keyword,
                        "path": audio_path
                    })
                else:
                    logger.warning(f"[新三国语音] 音频文件不存在: {audio_path}")
        return matched_audios

    def _needs_llm_response(self, message: str, event: AstrMessageEvent) -> bool:
        """判断消息是否需要 LLM 回复"""
        clean_message = message.strip()
        is_private = not event.message_obj.group_id
        
        # 检查是否以唤醒词前缀开头
        is_wake_word = clean_message.startswith(self.wake_word_prefix)
        if is_wake_word:
            logger.info(f"[新三国语音] 检测到唤醒词前缀 {self.wake_word_prefix}")
        
        # 检查消息中是否有 @ 机器人（使用 isinstance 进行类型检查）
        is_at_bot = False
        bot_id = str(event.message_obj.self_id)
        
        for comp in event.message_obj.message:
            if isinstance(comp, Comp.At):
                qq_id = getattr(comp, 'qq', None) or getattr(comp, 'target', None)
                if qq_id and str(qq_id) == bot_id:
                    is_at_bot = True
                    logger.info(f"[新三国语音] 检测到 @ 机器人")
                    break
        
        logger.info(f"[新三国语音] 判断结果: is_private={is_private}, is_at_bot={is_at_bot}, is_wake_word={is_wake_word}, private_llm_mode={self.private_chat_llm_mode}")
        
        # 如果是唤醒词前缀，只触发玩梗，不触发 LLM 回复
        if is_wake_word:
            logger.info(f"[新三国语音] 唤醒词消息，只触发玩梗，不需要 LLM 回复")
            return False
        
        # 私聊消息的 LLM 回复逻辑
        if is_private:
            if self.private_chat_llm_mode == "always":
                logger.info(f"[新三国语音] 私聊消息，模式为 always，需要 LLM 回复")
                return True
            elif self.private_chat_llm_mode == "never":
                logger.info(f"[新三国语音] 私聊消息，模式为 never，不需要 LLM 回复")
                return False
            logger.info(f"[新三国语音] 私聊消息，模式为 smart，进行智能判断")
        
        # 群聊：如果不是被 @，则不需要 LLM 回复
        if not is_private and not is_at_bot:
            logger.info(f"[新三国语音] 群聊普通消息，不需要 LLM 回复")
            return False
        
        # 智能判断：检查是否包含需要 LLM 回复的特征
        for pattern in self.need_llm_patterns:
            if re.search(pattern, clean_message):
                logger.info(f"[新三国语音] 消息包含特征词「{pattern}」，需要 LLM 回复")
                return True
        
        # 计算关键词占比
        if len(clean_message) > 0:
            keyword_chars = 0
            for rule in self.rules:
                keyword = rule.get("keyword", "")
                if keyword in clean_message:
                    keyword_chars += len(keyword)
            
            if keyword_chars / len(clean_message) < self.keyword_ratio_threshold:
                logger.info(f"[新三国语音] 关键词占比小于{self.keyword_ratio_threshold*100}%，有实际内容，需要 LLM 回复")
                return True
        
        logger.debug(f"[新三国语音] 判断为纯玩梗消息，不需要 LLM 回复")
        return False

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，匹配关键词并发送语音"""
        message = event.message_str.strip()
        if not message:
            return
        
        # 检查是否是插件自己的指令
        if message.startswith("/sanguo"):
            return
        
        # 检查是否仅群聊触发
        is_private = not event.message_obj.group_id
        if self.enable_group_only and is_private:
            logger.debug(f"[新三国语音] 私聊消息，不触发玩梗")
            return

        # 匹配关键词
        matched_audios = self._match_keywords(message)
        
        if not matched_audios:
            return
        
        # 选择语音
        if self.random_select:
            selected = random.choice(matched_audios)
            audios_to_send = [selected]
        else:
            audios_to_send = matched_audios
        
        # 发送语音消息
        for audio_info in audios_to_send:
            audio_path = audio_info["path"]
            keyword = audio_info["keyword"]
            
            logger.info(f"[新三国语音] 匹配关键词「{keyword}」，发送语音: {audio_path}")
            self.trigger_count += 1
            
            try:
                yield event.chain_result([
                    Comp.Record(file=audio_path, url=audio_path)
                ])
            except Exception as e:
                logger.error(f"[新三国语音] 发送语音失败: {e}")
                continue
        
        # 智能判断是否需要继续 LLM 回复
        if self._needs_llm_response(message, event):
            logger.info(f"[新三国语音] 消息需要 LLM 回复，主动请求 LLM")
            yield event.request_llm(prompt=message)
        else:
            logger.info(f"[新三国语音] 纯玩梗消息，停止事件传播")
        
        event.stop_event()

    @filter.command_group("sanguo")
    def sanguo_group(self):
        """新三国语音插件指令组"""
        pass

    @sanguo_group.command("help")
    async def sanguo_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = f"""🎭 新三国语音插件 帮助

📌 功能说明：
当聊天消息中包含新三国经典台词的关键词时，机器人会自动发送对应的语音片段。

🧠 智能回复：
• 纯玩梗消息 → 只发语音
• 有实际问题 → 发语音 + LLM 回复

⚙️ 当前配置：
• 仅群聊触发: {'是' if self.enable_group_only else '否'}
• 私聊 LLM 模式: {self.private_chat_llm_mode}
• 唤醒词前缀: {self.wake_word_prefix}
• 关键词占比阈值: {self.keyword_ratio_threshold*100}%
• 随机选择语音: {'是' if self.random_select else '否'}
• LLM 唤醒词数量: {len(self.need_llm_patterns)} 个

📋 可用指令：
• /sanguo help - 显示此帮助信息
• /sanguo list - 查看所有关键词列表
• /sanguo stats - 查看触发统计
• /sanguo reload - 重新加载规则配置

💡 提示：可在 WebUI 插件管理中修改配置！"""
        yield event.plain_result(help_text)

    @sanguo_group.command("list")
    async def sanguo_list(self, event: AstrMessageEvent):
        """列出所有关键词"""
        if not self.rules:
            yield event.plain_result("❌ 当前没有加载任何关键词规则")
            return
        
        keywords = [rule.get("keyword", "") for rule in self.rules if rule.get("keyword")]
        keywords = sorted(set(keywords))
        
        result = f"🎭 新三国语音关键词列表（共 {len(keywords)} 个）\n\n"
        result += "、".join(keywords)
        
        yield event.plain_result(result)

    @sanguo_group.command("stats")
    async def sanguo_stats(self, event: AstrMessageEvent):
        """查看统计信息"""
        audio_count = 0
        if os.path.exists(self.audio_dir):
            audio_count = len([f for f in os.listdir(self.audio_dir) if f.endswith('.mp3')])
        
        stats_text = f"""📊 新三国语音插件统计

📁 规则数量: {len(self.rules)} 条
🎵 音频文件: {audio_count} 个
🎯 本次运行触发次数: {self.trigger_count} 次
📂 音频目录: {self.audio_dir}
📂 数据目录: {self.data_dir}

⚙️ 配置信息：
• 仅群聊触发: {'是' if self.enable_group_only else '否'}
• 私聊 LLM 模式: {self.private_chat_llm_mode}
• 唤醒词前缀: {self.wake_word_prefix}
• 关键词占比阈值: {self.keyword_ratio_threshold*100}%
• LLM 唤醒词数量: {len(self.need_llm_patterns)} 个"""
        
        yield event.plain_result(stats_text)

    @sanguo_group.command("reload")
    async def sanguo_reload(self, event: AstrMessageEvent):
        """重新加载规则配置"""
        old_count = len(self.rules)
        self.rules = self._load_rules()
        new_count = len(self.rules)
        
        # 重新加载配置
        self.need_llm_patterns = self.config.get("llm_wake_patterns", DEFAULT_LLM_PATTERNS)
        self.keyword_ratio_threshold = self.config.get("keyword_ratio_threshold", 0.5)
        self.wake_word_prefix = self.config.get("wake_word_prefix", "/")
        self.enable_group_only = self.config.get("enable_group_only", True)
        self.random_select = self.config.get("random_select", True)
        self.private_chat_llm_mode = self.config.get("private_chat_llm_mode", "smart")
        
        yield event.plain_result(f"✅ 配置重新加载完成！\n规则: {old_count} 条 → {new_count} 条\nLLM 唤醒词: {len(self.need_llm_patterns)} 个\n私聊 LLM 模式: {self.private_chat_llm_mode}")

    async def terminate(self):
        """插件卸载时调用"""
        logger.info(f"[新三国语音] 插件已卸载，本次共触发 {self.trigger_count} 次")
