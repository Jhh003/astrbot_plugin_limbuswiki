"""
Auto-tagging module for Limbus Guide Plugin
Automatically tags chunks based on Limbus Company domain keywords
"""
import re
from typing import List, Dict, Set, Tuple


class Tagger:
    """Auto-tagger for Limbus Company content"""
    
    # Status effect keywords (English and Chinese)
    STATUS_KEYWORDS = {
        'burn': ['burn', '燃烧', '烧伤', 'burning'],
        'bleed': ['bleed', '流血', '出血', 'bleeding'],
        'tremor': ['tremor', '震颤', '颤抖'],
        'rupture': ['rupture', '破裂', '爆裂'],
        'sinking': ['sinking', '沉沦', '下沉'],
        'poise': ['poise', '蓄力', '架势', '姿态'],
        'charge': ['charge', '充能'],
    }
    
    # Mode/Content keywords
    MODE_KEYWORDS = {
        '主线': ['主线', '章节', 'story', 'main story'],
        '镜牢': ['镜牢', 'mirror dungeon', 'md', '镜像迷宫'],
        '铁道': ['铁道', 'railway', 'rr', 'refraction railway', '折射铁道'],
        '活动': ['活动', 'event', '限时'],
        '异想体': ['异想体', 'abnormality', 'abno'],
    }
    
    # Mechanics keywords
    MECHANICS_KEYWORDS = {
        '拼点/冲突': ['拼点', 'clash', '冲突', '硬币', 'coin', '速度', 'speed'],
        '罪孽/资源': ['罪孽', 'sin', '资源', 'resource', '共鸣', 'resonance', 
                    '暴食', '色欲', '懒惰', '暴怒', '忧郁', '傲慢', '嫉妒',
                    'gluttony', 'lust', 'sloth', 'wrath', 'gloom', 'pride', 'envy'],
        '属性/伤害类型': ['斩击', 'slash', '穿刺', 'pierce', '钝击', 'blunt', 
                       '抗性', 'resistance', '弱点', 'weakness', '伤害类型'],
        '精神/混乱': ['精神', 'sanity', '混乱', 'panic', 'sp', '理智'],
        '技能与被动': ['技能', 'skill', '被动', 'passive', '主动', 'active'],
        'EGO机制': ['ego', '侵蚀', 'corrosion', '腐蚀', 'erosion'],
        '结算顺序': ['结算', '回合', 'turn', '顺序', 'order', '流程'],
    }
    
    # Identity/Character keywords
    IDENTITY_KEYWORDS = {
        '人格': ['人格', 'identity', 'id', '000', '00', '三星', '二星', '一星'],
        '定位:输出': ['输出', 'dps', 'damage dealer', '伤害'],
        '定位:坦克': ['坦克', 'tank', '肉盾', '承伤'],
        '定位:辅助': ['辅助', 'support', 'buff', '增益'],
        '定位:控场': ['控场', 'control', 'cc', '控制'],
    }
    
    # Team building keywords
    TEAM_KEYWORDS = {
        '配队/阵容': ['配队', '阵容', 'team', 'lineup', '编队', '组队'],
        '轴/回合规划': ['轴', '回合规划', 'rotation', '循环'],
        'Boss打法': ['boss', '首领', '打法', 'strategy', '攻略'],
        '刷取/效率': ['刷', '效率', 'farm', 'grinding'],
    }
    
    # Character names (Limbus Company sinners)
    SINNER_NAMES = [
        'yi sang', '以撒', '异想',
        'faust', '浮士德',
        'don quixote', '堂吉诃德', '唐吉诃德',
        'ryoshu', '良秀', '龙秀',
        'meursault', '默尔索',
        'hong lu', '洪鹿', '红鹿',
        'heathcliff', '希斯克利夫',
        'ishmael', '以实玛利',
        'rodion', '罗季翁', '罗佳',
        'sinclair', '辛克莱',
        'outis', '奥提斯',
        'gregor', '格里高尔',
    ]
    
    def __init__(self):
        """Initialize tagger with compiled patterns"""
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for efficiency"""
        self.status_patterns = {}
        for status, keywords in self.STATUS_KEYWORDS.items():
            pattern = '|'.join(re.escape(kw) for kw in keywords)
            self.status_patterns[status] = re.compile(pattern, re.IGNORECASE)
        
        self.mode_patterns = {}
        for mode, keywords in self.MODE_KEYWORDS.items():
            pattern = '|'.join(re.escape(kw) for kw in keywords)
            self.mode_patterns[mode] = re.compile(pattern, re.IGNORECASE)
        
        self.mechanics_patterns = {}
        for mech, keywords in self.MECHANICS_KEYWORDS.items():
            pattern = '|'.join(re.escape(kw) for kw in keywords)
            self.mechanics_patterns[mech] = re.compile(pattern, re.IGNORECASE)
        
        self.identity_patterns = {}
        for identity, keywords in self.IDENTITY_KEYWORDS.items():
            pattern = '|'.join(re.escape(kw) for kw in keywords)
            self.identity_patterns[identity] = re.compile(pattern, re.IGNORECASE)
        
        self.team_patterns = {}
        for team, keywords in self.TEAM_KEYWORDS.items():
            pattern = '|'.join(re.escape(kw) for kw in keywords)
            self.team_patterns[team] = re.compile(pattern, re.IGNORECASE)
        
        # Sinner name pattern
        sinner_pattern = '|'.join(re.escape(name) for name in self.SINNER_NAMES)
        self.sinner_pattern = re.compile(sinner_pattern, re.IGNORECASE)
    
    def tag_chunk(self, content: str) -> Tuple[List[str], Dict]:
        """
        Tag a chunk of text
        
        Returns:
            Tuple of (tags list, entities dict)
        """
        tags: Set[str] = set()
        entities = {
            'statuses': [],
            'modes': [],
            'identities': [],
            'egos': [],
            'sinners': []
        }
        
        content_lower = content.lower()
        
        # Check status effects
        for status, pattern in self.status_patterns.items():
            if pattern.search(content):
                tags.add(f'状态:{status.capitalize()}')
                if status not in entities['statuses']:
                    entities['statuses'].append(status)
        
        # Check modes
        for mode, pattern in self.mode_patterns.items():
            if pattern.search(content):
                tags.add(mode)
                if mode not in entities['modes']:
                    entities['modes'].append(mode)
        
        # Check mechanics
        for mech, pattern in self.mechanics_patterns.items():
            if pattern.search(content):
                tags.add(mech)
        
        # Check identity keywords
        for identity, pattern in self.identity_patterns.items():
            if pattern.search(content):
                tags.add(identity)
        
        # Check team building keywords
        for team, pattern in self.team_patterns.items():
            if pattern.search(content):
                tags.add(team)
        
        # Extract sinner names
        sinner_matches = self.sinner_pattern.findall(content)
        for match in sinner_matches:
            normalized = self._normalize_sinner_name(match)
            if normalized and normalized not in entities['sinners']:
                entities['sinners'].append(normalized)
                tags.add(f'角色:{normalized}')
        
        # Check for EGO mentions
        if re.search(r'ego|E\.G\.O', content, re.IGNORECASE):
            tags.add('EGO')
            # Try to extract EGO names (pattern: "EGO:xxx" or "EGO：xxx")
            ego_matches = re.findall(r'[Ee][Gg][Oo][：:]\s*([^\s,，。]+)', content)
            for ego in ego_matches:
                if ego not in entities['egos']:
                    entities['egos'].append(ego)
        
        # Check for specific identity patterns (e.g., "人格：xxx")
        identity_matches = re.findall(r'人格[：:]\s*([^\s,，。]+)', content)
        for identity in identity_matches:
            if identity not in entities['identities']:
                entities['identities'].append(identity)
        
        # Add meta tags based on content patterns
        if re.search(r'新手|入门|基础|教程', content):
            tags.add('新手入门')
        
        if re.search(r'版本|更新|patch|改动', content, re.IGNORECASE):
            tags.add('版本/更新')
        
        if re.search(r'资源|养成|材料|升级', content):
            tags.add('资源/养成')
        
        if re.search(r'FAQ|问答|Q\s*[：:]|A\s*[：:]', content, re.IGNORECASE):
            tags.add('FAQ')
        
        return list(tags), entities
    
    def _normalize_sinner_name(self, name: str) -> str:
        """Normalize sinner name to Chinese"""
        name_lower = name.lower().strip()
        
        name_mapping = {
            'yi sang': '以撒', '以撒': '以撒', '异想': '以撒',
            'faust': '浮士德', '浮士德': '浮士德',
            'don quixote': '堂吉诃德', '堂吉诃德': '堂吉诃德', '唐吉诃德': '堂吉诃德',
            'ryoshu': '良秀', '良秀': '良秀', '龙秀': '良秀',
            'meursault': '默尔索', '默尔索': '默尔索',
            'hong lu': '洪鹿', '洪鹿': '洪鹿', '红鹿': '洪鹿',
            'heathcliff': '希斯克利夫', '希斯克利夫': '希斯克利夫',
            'ishmael': '以实玛利', '以实玛利': '以实玛利',
            'rodion': '罗季翁', '罗季翁': '罗季翁', '罗佳': '罗季翁',
            'sinclair': '辛克莱', '辛克莱': '辛克莱',
            'outis': '奥提斯', '奥提斯': '奥提斯',
            'gregor': '格里高尔', '格里高尔': '格里高尔',
        }
        
        return name_mapping.get(name_lower, name)
    
    def process_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """
        Process multiple chunks and add tags/entities
        
        Args:
            chunks: List of chunk dicts with 'content' key
            
        Returns:
            Chunks with 'tags' and 'entities' added
        """
        for chunk in chunks:
            tags, entities = self.tag_chunk(chunk['content'])
            chunk['tags'] = tags
            chunk['entities'] = entities
        
        return chunks
    
    def get_tag_statistics(self, chunks: List[Dict]) -> Dict[str, int]:
        """Get statistics of tags across all chunks"""
        stats = {}
        for chunk in chunks:
            for tag in chunk.get('tags', []):
                stats[tag] = stats.get(tag, 0) + 1
        return dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))
