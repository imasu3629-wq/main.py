import discord
from discord import app_commands
import requests
import os
from flask import Flask
from threading import Thread
from database import (
    init_db, get_cached_uuid, save_uuid_cache,
    register_player, update_stats, is_registered, is_registered_by_discord,
    get_registered_by_discord, get_ranking_by_fkdr, get_ranking_by_star
)

# --- 24時間稼働設定 ---
app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- 環境変数 ---
TOKEN = os.environ['DISCORD_TOKEN']
current_api_key = os.environ['HYPIXEL_KEY']
AUTHORIZED_USERS = [1278574483195559977]

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# --- UUID取得ヘルパー（キャッシュ付き） ---
def fetch_uuid(mcid: str):
    cached = get_cached_uuid(mcid)
    if cached:
        return cached
    res = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{mcid}")
    if res.status_code != 200:
        return None
    uuid = res.json().get('id')
    if uuid:
        save_uuid_cache(mcid, uuid)
    return uuid


# --- Hypixel stats取得ヘルパー ---
def fetch_hypixel_stats(uuid: str):
    url = f"https://api.hypixel.net/v2/player?key={current_api_key}&uuid={uuid}"
    res = requests.get(url).json()
    if not res.get("player"):
        return None, None
    p = res["player"]
    bw = p.get("stats", {}).get("Bedwars", {})
    star = p.get("achievements", {}).get("bedwars_level", 0)
    fk = bw.get("final_kills_bedwars", 0)
    fd = bw.get("final_deaths_bedwars", 1)
    fkdr = round(fk / max(fd, 1), 2)
    return star, fkdr


# --- ランキング選択View（最初に表示） ---
class RankingSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="⚔️ FKDR順", style=discord.ButtonStyle.primary)
    async def fkdr_ranking(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = get_ranking_by_fkdr()
        embed = build_ranking_embed(rows, "fkdr")
        await interaction.response.edit_message(content=None, embed=embed, view=RankingBackView())

    @discord.ui.button(label="⭐ スター順", style=discord.ButtonStyle.secondary)
    async def star_ranking(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = get_ranking_by_star()
        embed = build_ranking_embed(rows, "star")
        await interaction.response.edit_message(content=None, embed=embed, view=RankingBackView())


# --- ランキング表示後の戻るView ---
class RankingBackView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="↩️ 選択に戻る", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="📊 どちらのランキングを表示しますか？",
            embed=None,
            view=RankingSelectView()
        )


def build_ranking_embed(rows, mode: str):
    medals = ["🥇", "🥈", "🥉"]
    if mode == "fkdr":
        title = "⚔️ FKDR ランキング TOP10"
        color = 0xe74c3c
        lines = [
            f"{medals[i] if i < 3 else f'`{i+1}.`'} **{r['mcid']}** — FKDR: `{r['fkdr']}`"
            for i, r in enumerate(rows)
        ]
    else:
        title = "⭐ スター ランキング TOP10"
        color = 0xf1c40f
        lines = [
            f"{medals[i] if i < 3 else f'`{i+1}.`'} **{r['mcid']}** — ⭐{r['star']}"
            for i, r in enumerate(rows)
        ]
    embed = discord.Embed(
        title=title,
        description="\n".join(lines) if lines else "データがありません",
        color=color
    )
    embed.set_footer(text="↩️ 選択に戻るで切り替えできます")
    return embed


# ====================
# コマンド
# ====================

@bot.event
async def on_ready():
    init_db()
    try:
        synced = await tree.sync()
        print(f"✅ {len(synced)}個のコマンドを同期しました")
    except Exception as e:
        print(f"❌ 同期エラー: {e}")
    print(f'✅ Logged in as {bot.user.name}')


# --- /register ---
@tree.command(name="register", description="MCIDを登録してBedwars戦績を記録します")
async def register(interaction: discord.Interaction, mcid: str):
    await interaction.response.defer(ephemeral=True)
    try:
        uuid = fetch_uuid(mcid)
        if not uuid:
            await interaction.followup.send("❌ プレイヤーが見つかりません。MCIDを確認してください。", ephemeral=True)
            return

        if is_registered(uuid):
            await interaction.followup.send(f"⚠️ `{mcid}` はすでに登録されています。", ephemeral=True)
            return

        star, fkdr = fetch_hypixel_stats(uuid)
        if star is None:
            await interaction.followup.send("❌ Hypixelからデータを取得できませんでした。", ephemeral=True)
            return

        register_player(uuid, mcid, interaction.user.id, star, fkdr)

        embed = discord.Embed(title="✅ 登録完了", color=0x2ecc71)
        embed.add_field(name="MCID", value=mcid, inline=True)
        embed.add_field(name="⭐ Star", value=str(star), inline=True)
        embed.add_field(name="⚔️ FKDR", value=str(fkdr), inline=True)
        embed.set_footer(text="ランキングに反映されました")
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーが発生しました: {e}", ephemeral=True)


# --- /registered ---
@tree.command(name="registered", description="自分が登録したMCID一覧を表示します")
async def registered(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        rows = get_registered_by_discord(interaction.user.id)
        if not rows:
            await interaction.followup.send("📭 登録されたMCIDはありません。`/register [MCID]` で登録できます。", ephemeral=True)
            return

        embed = discord.Embed(title="📋 登録済みMCID一覧", color=0x3498db)
        lines = [
            f"**{r['mcid']}** — ⭐{r['star']} FKDR:`{r['fkdr']}` （更新: {r['updated_at'][:10]}）"
            for r in rows
        ]
        embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラー: {e}", ephemeral=True)


# --- /refresh ---
@tree.command(name="refresh", description="登録済みMCIDの戦績を最新データに更新します")
async def refresh(interaction: discord.Interaction, mcid: str):
    await interaction.response.defer(ephemeral=True)
    try:
        uuid = fetch_uuid(mcid)
        if not uuid:
            await interaction.followup.send("❌ プレイヤーが見つかりません。", ephemeral=True)
            return

        if not is_registered_by_discord(interaction.user.id, uuid):
            await interaction.followup.send("❌ このMCIDはあなたが登録したものではありません。", ephemeral=True)
            return

        star, fkdr = fetch_hypixel_stats(uuid)
        if star is None:
            await interaction.followup.send("❌ Hypixelからデータを取得できませんでした。", ephemeral=True)
            return

        # 最新MCIDも更新（名前変更対応）
        update_stats(uuid, mcid, star, fkdr)

        embed = discord.Embed(title="🔄 戦績を更新しました", color=0x9b59b6)
        embed.add_field(name="MCID", value=mcid, inline=True)
        embed.add_field(name="⭐ Star", value=str(star), inline=True)
        embed.add_field(name="⚔️ FKDR", value=str(fkdr), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラー: {e}", ephemeral=True)


# --- /ranking ---
@tree.command(name="ranking", description="BedwarsランキングをFKDR順またはスター順で表示します")
async def ranking(interaction: discord.Interaction):
    await interaction.response.send_message(
        content="📊 どちらのランキングを表示しますか？",
        view=RankingSelectView()
    )


# --- /stats（既存・UUID対応に改良） ---
@tree.command(name="stats", description="Hypixelの戦績を表示します")
async def stats(interaction: discord.Interaction, mcid: str):
    await interaction.response.defer()
    try:
        uuid = fetch_uuid(mcid)
        if not uuid:
            await interaction.followup.send("❌ プレイヤーが見つかりません。")
            return
        star, fkdr = fetch_hypixel_stats(uuid)
        if star is None:
            await interaction.followup.send("❌ Hypixelにデータがありません。")
            return
        embed = discord.Embed(title=f"{mcid} の戦績", color=0x00ff00)
        embed.add_field(name="⭐ Star", value=str(star), inline=True)
        embed.add_field(name="⚔️ FKDR", value=str(fkdr), inline=True)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラー: {e}")


# --- /skin（既存） ---
@tree.command(name="skin", description="指定したMCIDのスキン画像を表示します")
async def skin(interaction: discord.Interaction, mcid: str):
    await interaction.response.defer()
    try:
        uuid = fetch_uuid(mcid)
        if not uuid:
            await interaction.followup.send("❌ プレイヤーが見つかりません。")
            return
        render_url = f"https://visage.surgeplay.com/full/384/{uuid}.png"
        raw_skin_url = f"https://visage.surgeplay.com/skin/{uuid}.png"
        embed = discord.Embed(title=f"👕 {mcid} のスキン", color=0x9b59b6)
        embed.set_image(url=render_url)
        embed.add_field(name="📥 配布用データ", value=f"[この画像を保存して適用]({raw_skin_url})", inline=False)
        await interaction.followup.send(embed=embed)
    except:
        await interaction.followup.send("⚠️ スキン取得エラー")


# --- /history（既存） ---
@tree.command(name="history", description="Laby.netから最新の変更履歴をすべて取得します")
async def history(interaction: discord.Interaction, mcid: str):
    await interaction.response.defer()
    try:
        uuid = fetch_uuid(mcid)
        if not uuid:
            await interaction.followup.send("❌ プレイヤーが見つかりません。")
            return
        headers = {"User-Agent": "Mozilla/5.0"}
        h_res = requests.get(f"https://laby.net/api/v3/user/{uuid}/profile", headers=headers)
        if h_res.status_code != 200:
            await interaction.followup.send("❌ Laby.netからデータを取得できませんでした。")
            return
        data = h_res.json()
        history_data = data.get("username_history", [])
        if history_data:
            embed = discord.Embed(title=f"📜 {mcid} のID変更履歴", color=0x3498db)
            lines = []
            for entry in reversed(history_data):
                name = entry.get('username')
                changed_at = entry.get('changed_at')
                if changed_at:
                    date = changed_at[:10].replace("-", "/")
                    lines.append(f"📅 `{date}` ➔ **{name}**")
                else:
                    lines.append(f"🌱 `最初のID` ➔ **{name}**")
            embed.description = "\n".join(lines)
            embed.set_footer(text="Data provided by Laby.net")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"ℹ️ {mcid} の履歴データが空でした。")
    except:
        await interaction.followup.send("⚠️ 履歴取得中にエラーが発生しました。")


# --- /setkey（既存） ---
@tree.command(name="setkey", description="APIキーを更新")
async def setkey(interaction: discord.Interaction, new_key: str):
    global current_api_key
    if interaction.user.id not in AUTHORIZED_USERS:
        await interaction.response.send_message("❌ 権限なし", ephemeral=True)
        return
    current_api_key = new_key
    await interaction.response.send_message("✅ 更新完了", ephemeral=True)


keep_alive()
bot.run(TOKEN)
