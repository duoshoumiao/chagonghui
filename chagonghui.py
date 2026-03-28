import json  
import os  
import io  
import base64  
import asyncio  
import logging  
from pathlib import Path  
import requests  
from PIL import Image, ImageDraw, ImageFont  
from hoshino import Service, priv  
  
logger = logging.getLogger(__name__)  
  
# 扫描结果存储路径（与原插件保持一致）  
SCAN_DATA_DIR = Path(os.path.expanduser('~/.hoshino/clan_scan/'))  
SCAN_DATA_DIR.mkdir(parents=True, exist_ok=True)  
SCAN_FILE = SCAN_DATA_DIR / 'clan_ranking_global.json'  
# ======================== GitHub 配置 ========================  
# 个人访问令牌，建议通过环境变量设置: export GITHUB_PAT="ghp_xxxx"  
GITHUB_PAT = os.environ.get('GITHUB_PAT', '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')  
GITHUB_REPO = 'duoshoumiao/chagonghui'  
GITHUB_FILE_PATH = 'clan_scan/clan_ranking_global.json'  
GITHUB_API_BASE = f'https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}'  
  
# ======================== 字体查找 ========================  
def _get_github_file_sha():  
    """获取 GitHub 上文件的当前 SHA（用于更新文件时必须提供）"""  
    headers = {  
        'Authorization': f'token {GITHUB_PAT}',  
        'Accept': 'application/vnd.github.v3+json',  
    }  
    resp = requests.get(GITHUB_API_BASE, headers=headers)  
    if resp.status_code == 200:  
        return resp.json().get('sha')  
    return None

  
def _find_cjk_font():  
    """  
    在 hoshino/modules/ 下扫描所有子包的 fonts/SourceHanSansCN-Medium.otf，  
    找不到则回退到 Windows 系统自带中文字体。  
    """  
    target_name = "SourceHanSansCN-Medium.otf"  
  
    # 1) 扫描 hoshino/modules/*/fonts/  
    modules_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # hoshino/modules/  
    if os.path.isdir(modules_dir):  
        for name in os.listdir(modules_dir):  
            candidate = os.path.join(modules_dir, name, 'fonts', target_name)  
            if os.path.isfile(candidate):  
                logger.info(f'[公会查询] 找到字体: {candidate}')  
                return candidate  
  
    # 2) Windows 系统字体回退  
    system_fonts = [  
        r'C:\Windows\Fonts\msyh.ttc',    # 微软雅黑  
        r'C:\Windows\Fonts\simhei.ttf',   # 黑体  
        r'C:\Windows\Fonts\simsun.ttc',   # 宋体  
    ]  
    for fp in system_fonts:  
        if os.path.isfile(fp):  
            logger.info(f'[公会查询] 使用系统字体: {fp}')  
            return fp  
  
    # 3) 都找不到  
    raise FileNotFoundError(  
        f'找不到中文字体 {target_name}，'  
        f'已搜索 {modules_dir}/*/fonts/ 及 Windows 系统字体目录'  
    )  
  
  
FONT_FILE = _find_cjk_font()  
  
  
sv = Service(  
    name='公会查询',  
    visible=True,  
    enable_on_default=False,  
    help_='【查会长 关键词】按会长名搜索公会\n【查公会 关键词】按公会名搜索公会\n【查排名 数字】按排名查询公会，支持逗号分隔多个排名',  
)  
  
  
# ======================== 图片渲染 ========================  
  
def generate_clan_image(clans, title=''):  
    """  
    将公会信息列表渲染为横向卡片网格图片。  
    根据数量自动调整列数和画布尺寸。  
    """  
    if not clans:  
        return None  
  
    count = len(clans)  
  
    # ---------- 根据数量动态决定列数 ----------  
    if count == 1:  
        COLUMNS = 1  
    elif count == 2:  
        COLUMNS = 2  
    elif count <= 6:  
        COLUMNS = 3  
    else:  
        COLUMNS = 4  
  
    # ---------- 卡片与间距参数 ----------  
    CARD_W = 420  
    CARD_H = 140  
    GAP_X = 12  
    GAP_Y = 12  
    MARGIN = 24  
    TITLE_H = 50  
  
    # ---------- 字体 ----------  
    title_font = ImageFont.truetype(FONT_FILE, 26)  
    label_font = ImageFont.truetype(FONT_FILE, 16)  
    rank_font  = ImageFont.truetype(FONT_FILE, 30)  
    value_font = ImageFont.truetype(FONT_FILE, 15)  
  
    # ---------- 计算画布尺寸 ----------  
    rows = (count + COLUMNS - 1) // COLUMNS  
    title_area = TITLE_H if title else 0  
    img_w = MARGIN * 2 + COLUMNS * CARD_W + max(COLUMNS - 1, 0) * GAP_X  
    img_h = MARGIN * 2 + title_area + rows * CARD_H + max(rows - 1, 0) * GAP_Y  
  
    image = Image.new('RGB', (img_w, img_h), (255, 252, 245))  
    draw = ImageDraw.Draw(image)  
  
    # ---------- 绘制标题 ----------  
    if title:  
        draw.text((MARGIN, MARGIN - 4), title, fill=(80, 60, 40), font=title_font)  
  
    # ---------- 绘制卡片 ----------  
    for idx, c in enumerate(clans):  
        col = idx % COLUMNS  
        row = idx // COLUMNS  
        x0 = MARGIN + col * (CARD_W + GAP_X)  
        y0 = MARGIN + title_area + row * (CARD_H + GAP_Y)  
        x1 = x0 + CARD_W  
        y1 = y0 + CARD_H  
  
        # 卡片背景 + 圆角边框  
        draw.rounded_rectangle([x0, y0, x1, y1], radius=10,  
                               fill=(255, 255, 255), outline=(210, 200, 185), width=1)  
  
        # 左侧排名  
        rank_text = f"#{c['rank']}"  
        draw.text((x0 + 12, y0 + 12), rank_text, fill=(50, 50, 50), font=rank_font)  
  
        # 右侧信息  
        info_x = x0 + 110  
        line_h = 22  
  
        clan_name = c.get('clan_name', '')  
        draw.text((info_x, y0 + 10), f"公会: {clan_name}", fill=(40, 40, 40), font=label_font)  
  
        leader = c.get('leader_name', '')  
        draw.text((info_x, y0 + 10 + line_h), f"会长: {leader}", fill=(100, 90, 80), font=label_font)  
  
        damage = c.get('damage', 0)  
        damage_str = f"{damage:,}" if isinstance(damage, int) else str(damage)  
        draw.text((info_x, y0 + 10 + line_h * 2), f"总伤害: {damage_str}", fill=(100, 90, 80), font=value_font)  
  
        member = c.get('member_num', 0)  
        grade = c.get('grade_rank', '-')  
        draw.text((info_x, y0 + 10 + line_h * 3), f"成员: {member}/30", fill=(100, 90, 80), font=value_font)  
        draw.text((info_x + 160, y0 + 10 + line_h * 3), f"上期: {grade}位", fill=(150, 130, 100), font=value_font)  
  
        draw.text((x0 + 12, y0 + CARD_H - 28), f"{member}/30",  
                  fill=(170, 160, 140), font=value_font)  
  
    # ---------- 编码为 base64 ----------  
    buf = io.BytesIO()  
    image.save(buf, format='PNG')  
    b64 = base64.b64encode(buf.getvalue()).decode()  
    return f'[CQ:image,file=base64://{b64}]'
  
  
# ======================== 指令处理 ========================  
  
MAX_RESULTS = 80  # 最大显示数量  
  
  
@sv.on_prefix('查会长')  
async def search_clan_leader(bot, ev):  
    keyword = ev.message.extract_plain_text().strip()  
    if not keyword:  
        return await bot.send(ev, '请输入要搜索的会长关键词，例如：查会长 栞栞')  
  
    if not SCAN_FILE.exists():  
        return await bot.send(ev, '尚未扫描公会数据，请管理员发送【扫描公会】')  
  
    with open(SCAN_FILE, 'r', encoding='utf-8') as f:  
        all_clans = json.load(f)  
  
    results = [c for c in all_clans.values() if keyword in c.get('leader_name', '')]  
    if not results:  
        return await bot.send(ev, f'未找到会长名包含"{keyword}"的公会')  
  
    results.sort(key=lambda x: x['rank'])  
    total = len(results)  
    show = results[:MAX_RESULTS]  
    title = f'查会长「{keyword}」 找到{total}个结果' + (f'（仅显示前{MAX_RESULTS}条）' if total > MAX_RESULTS else '')  
  
    img = generate_clan_image(show, title=title)  
    if img:  
        await bot.send(ev, img)  
    else:  
        await bot.send(ev, '图片生成失败')  
  
  
@sv.on_prefix('查公会')  
async def search_clan_name(bot, ev):  
    keyword = ev.message.extract_plain_text().strip()  
    if not keyword:  
        return await bot.send(ev, '请输入要搜索的公会名关键词，例如：查公会 栞栞')  
  
    if not SCAN_FILE.exists():  
        return await bot.send(ev, '尚未扫描公会数据，请管理员发送【扫描公会】')  
  
    with open(SCAN_FILE, 'r', encoding='utf-8') as f:  
        all_clans = json.load(f)  
  
    results = [c for c in all_clans.values() if keyword in c.get('clan_name', '')]  
    if not results:  
        return await bot.send(ev, f'未找到公会名包含"{keyword}"的公会')  
  
    results.sort(key=lambda x: x['rank'])  
    total = len(results)  
    show = results[:MAX_RESULTS]  
    title = f'查公会「{keyword}」 找到{total}个结果' + (f'（仅显示前{MAX_RESULTS}条）' if total > MAX_RESULTS else '')  
  
    img = generate_clan_image(show, title=title)  
    if img:  
        await bot.send(ev, img)  
    else:  
        await bot.send(ev, '图片生成失败')  
  
  
@sv.on_prefix('查排名')  
async def search_clan_rank(bot, ev):  
    keyword = ev.message.extract_plain_text().strip()  
    if not keyword:  
        return await bot.send(ev, '请输入要查询的排名，例如：\n  1. 单个排名：查排名 100\n  2. 多个排名：查排名 100,200,300\n  3. 排名范围：查排名 1-10')  
  
    if not SCAN_FILE.exists():  
        return await bot.send(ev, '尚未扫描公会数据，请管理员发送【扫描公会】')  
  
    # 解析输入：支持 单个排名、逗号分隔多排名、范围（1-10）  
    target_ranks = []  
    error_strs = []  
    parts = [p.strip() for p in keyword.split(',')]  
  
    for part in parts:  
        if '-' in part:  
            range_parts = part.split('-', 1)  
            if len(range_parts) != 2:  
                error_strs.append(part)  
                continue  
            start_str, end_str = range_parts  
            if not (start_str.isdigit() and end_str.isdigit()):  
                error_strs.append(part)  
                continue  
            start = int(start_str)  
            end = int(end_str)  
            if start > end:  
                start, end = end, start  
            if end - start + 1 > 100:  
                return await bot.send(ev, f'范围查询最多支持100个排名，当前范围({start}-{end})包含{end - start + 1}个排名，请缩小范围')  
            target_ranks.extend(range(start, end + 1))  
        elif part.isdigit():  
            target_ranks.append(int(part))  
        else:  
            error_strs.append(part)  
  
    if error_strs:  
        return await bot.send(ev, f'排名格式有误："{", ".join(error_strs)}"，支持格式：\n  1. 单个排名：查排名 100\n  2. 多个排名：查排名 100,200,300\n  3. 排名范围：查排名 1-10')  
  
    target_ranks = sorted(list(set(target_ranks)))  
  
    with open(SCAN_FILE, 'r', encoding='utf-8') as f:  
        all_clans = json.load(f)  
  
    # 收集匹配的公会 dict  
    matched = []  
    not_found = []  
    for rank in target_ranks:  
        c = all_clans.get(str(rank))  
        if c:  
            matched.append(c)  
        else:  
            not_found.append(str(rank))  
  
    if not matched:  
        return await bot.send(ev, f'未找到排名 {", ".join(not_found)} 的公会数据')  
  
    show = matched[:MAX_RESULTS]  
    title = f'查排名 共{len(matched)}条结果' + (f'（仅显示前{MAX_RESULTS}条）' if len(matched) > MAX_RESULTS else '')  
    if not_found:  
        nf_preview = not_found[:10]  
        title += f'  未找到: {", ".join(nf_preview)}' + ('...' if len(not_found) > 10 else '')  
  
    img = generate_clan_image(show, title=title)  
    if img:  
        await bot.send(ev, img)  
    else:  
        await bot.send(ev, '图片生成失败')
        
@sv.on_fullmatch('上传公会数据')  
async def upload_clan_data(bot, ev):  
    if not priv.check_priv(ev, priv.ADMIN):  
        return await bot.send(ev, '仅管理员可执行此操作')  
    if not GITHUB_PAT:  
        return await bot.send(ev, '未配置 GitHub 个人访问令牌，请设置环境变量 GITHUB_PAT')  
    if not SCAN_FILE.exists():  
        return await bot.send(ev, '本地公会数据文件不存在，无法上传')  
  
    await bot.send(ev, '正在上传公会数据到 GitHub...')  
  
    try:  
        with open(SCAN_FILE, 'r', encoding='utf-8') as f:  
            content = f.read()  
        content_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')  
  
        headers = {  
            'Authorization': f'token {GITHUB_PAT}',  
            'Accept': 'application/vnd.github.v3+json',  
        }  
  
        sha = _get_github_file_sha()  
        payload = {  
            'message': '更新公会排名数据',  
            'content': content_b64,  
            'branch': 'main',  
        }  
        if sha:  
            payload['sha'] = sha  
  
        resp = requests.put(GITHUB_API_BASE, json=payload, headers=headers)  
        if resp.status_code in (200, 201):  
            await bot.send(ev, '公会数据已成功上传到 GitHub！')  
        else:  
            await bot.send(ev, f'上传失败: HTTP {resp.status_code}\n{resp.json().get("message", "")}')  
    except Exception as e:  
        logger.exception('上传公会数据失败')  
        await bot.send(ev, f'上传失败: {e}')

@sv.on_fullmatch('更新公会数据')  
async def download_clan_data(bot, ev):  
    if not priv.check_priv(ev, priv.ADMIN):  
        return await bot.send(ev, '仅管理员可执行此操作')  
    if not GITHUB_PAT:  
        return await bot.send(ev, '未配置 GitHub 个人访问令牌，请设置环境变量 GITHUB_PAT')  
  
    await bot.send(ev, '正在从 GitHub 下载公会数据...')  
  
    try:  
        headers = {  
            'Authorization': f'token {GITHUB_PAT}',  
            'Accept': 'application/vnd.github.v3+json',  
        }  
        resp = requests.get(GITHUB_API_BASE, headers=headers)  
        if resp.status_code != 200:  
            return await bot.send(ev, f'下载失败: HTTP {resp.status_code}\n{resp.json().get("message", "")}')  
  
        data = resp.json()  
        content_b64 = data.get('content', '')  
        # GitHub 返回的 base64 内容可能包含换行符，需要去除  
        content_b64 = content_b64.replace('\n', '')  
        content = base64.b64decode(content_b64).decode('utf-8')  
  
        # 验证 JSON 格式  
        json.loads(content)  
  
        SCAN_DATA_DIR.mkdir(parents=True, exist_ok=True)  
        with open(SCAN_FILE, 'w', encoding='utf-8') as f:  
            f.write(content)  
  
        await bot.send(ev, '公会数据已成功从 GitHub 更新到本地！')  
    except json.JSONDecodeError:  
        await bot.send(ev, '下载的文件不是有效的 JSON 格式')  
    except Exception as e:  
        logger.exception('下载公会数据失败')  
        await bot.send(ev, f'下载失败: {e}')        
       