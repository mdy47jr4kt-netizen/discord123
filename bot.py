import discord
from discord.ext import commands
import sqlite3
import os

DB_NAME = 'items.db'

# === БАЗА ДАННЫХ ===
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS shop_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT,
            price INTEGER,
            role_id INTEGER
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER,
            item_name TEXT,
            quantity INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, item_name)
        )
    ''')
    conn.commit()
    conn.close()

def get_balance(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def set_balance(user_id, amount):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO users (user_id, balance) VALUES (?, ?)', (user_id, amount))
    conn.commit()
    conn.close()

def add_balance(user_id, amount):
    new_balance = get_balance(user_id) + amount
    set_balance(user_id, new_balance)
    return new_balance

def create_item(name, description, price, role_id=None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO shop_items (name, description, price, role_id) VALUES (?, ?, ?, ?)',
                    (name, description, price, role_id))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def update_item(name, description=None, price=None, role_id=None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    fields = []
    params = []
    if description is not None:
        fields.append('description = ?')
        params.append(description)
    if price is not None:
        fields.append('price = ?')
        params.append(price)
    if role_id is not None:
        fields.append('role_id = ?')
        params.append(role_id)
    if not fields:
        conn.close()
        return False
    params.append(name)
    cur.execute(f'UPDATE shop_items SET {", ".join(fields)} WHERE name = ?', params)
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated

def get_item(name):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT name, description, price, role_id FROM shop_items WHERE name = ?', (name,))
    row = cur.fetchone()
    conn.close()
    return row

def get_all_items():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT name, description, price, role_id FROM shop_items')
    rows = cur.fetchall()
    conn.close()
    return rows

def add_to_inventory(user_id, item_name, quantity=1):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO inventory (user_id, item_name, quantity) 
        VALUES (?, ?, ?) 
        ON CONFLICT(user_id, item_name) DO UPDATE SET quantity = quantity + ?
    ''', (user_id, item_name, quantity, quantity))
    conn.commit()
    conn.close()

def remove_from_inventory(user_id, item_name, quantity=1):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT quantity FROM inventory WHERE user_id = ? AND item_name = ?', (user_id, item_name))
    row = cur.fetchone()
    if not row or row[0] < quantity:
        conn.close()
        return False
    if row[0] == quantity:
        cur.execute('DELETE FROM inventory WHERE user_id = ? AND item_name = ?', (user_id, item_name))
    else:
        cur.execute('UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_name = ?',
                    (quantity, user_id, item_name))
    conn.commit()
    conn.close()
    return True

def get_inventory(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT item_name, quantity FROM inventory WHERE user_id = ?', (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def has_item(user_id, item_name):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT quantity FROM inventory WHERE user_id = ? AND item_name = ?', (user_id, item_name))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

# === БОТ ===
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    init_db()
    print(f'✅ Бот {bot.user} запущен!')

@bot.command()
async def item(ctx, name: str, price: int, description: str = None, role_id: int = None):
    existing = get_item(name)
    if existing:
        update_item(name, description, price, role_id)
        await ctx.send(f'✅ Предмет **{name}** обновлён!')
    else:
        success = create_item(name, description or 'Нет описания', price, role_id)
        if success:
            await ctx.send(f'✅ Создан предмет **{name}** (цена: {price} монет)')
        else:
            await ctx.send('❌ Ошибка: возможно, предмет уже существует.')

@bot.command()
async def info(ctx, *, name: str):
    item = get_item(name)
    if not item:
        await ctx.send(f'❌ Предмет **{name}** не найден.')
        return
    name, desc, price, role_id = item
    role_text = f'Требуется роль: <@&{role_id}>' if role_id else 'Роль не требуется'
    embed = discord.Embed(title=f'📦 {name}', description=desc, color=0x00ff00)
    embed.add_field(name='Цена', value=f'{price} монет', inline=True)
    embed.add_field(name='Роль', value=role_text, inline=True)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def add_money(ctx, member: discord.Member, amount: int):
    add_balance(member.id, amount)
    await ctx.send(f'✅ {member.mention} получил {amount} монет. Баланс: {get_balance(member.id)}')

@bot.command()
@commands.has_permissions(administrator=True)
async def take_money(ctx, member: discord.Member, amount: int):
    if get_balance(member.id) < amount:
        await ctx.send(f'❌ У {member.mention} недостаточно денег.')
        return
    add_balance(member.id, -amount)
    await ctx.send(f'✅ У {member.mention} забрали {amount} монет. Баланс: {get_balance(member.id)}')

@bot.command()
async def give_money(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send('❌ Сумма должна быть больше 0.')
        return
    if get_balance(ctx.author.id) < amount:
        await ctx.send('❌ У вас недостаточно денег.')
        return
    add_balance(ctx.author.id, -amount)
    add_balance(member.id, amount)
    await ctx.send(f'✅ {ctx.author.mention} передал {amount} монет {member.mention}')

@bot.command()
async def sell(ctx, item_name: str, member: discord.Member, price: int):
    if price <= 0:
        await ctx.send('❌ Цена должна быть больше 0.')
        return
    if has_item(ctx.author.id, item_name) == 0:
        await ctx.send(f'❌ У вас нет предмета **{item_name}**.')
        return
    if get_balance(member.id) < price:
        await ctx.send(f'❌ У {member.mention} недостаточно денег.')
        return
    item = get_item(item_name)
    if not item:
        await ctx.send(f'❌ Предмет **{item_name}** не существует в магазине.')
        return
    
    remove_from_inventory(ctx.author.id, item_name)
    add_to_inventory(member.id, item_name)
    add_balance(ctx.author.id, price)
    add_balance(member.id, -price)
    await ctx.send(f'✅ {ctx.author.mention} продал **{item_name}** {member.mention} за {price} монет')

@bot.command()
@commands.has_permissions(administrator=True)
async def add_item(ctx, member: discord.Member, item_name: str, quantity: int = 1):
    if not get_item(item_name):
        await ctx.send(f'❌ Предмет **{item_name}** не найден в магазине.')
        return
    add_to_inventory(member.id, item_name, quantity)
    await ctx.send(f'✅ {member.mention} получил {quantity} шт. **{item_name}**')

@bot.command()
@commands.has_permissions(administrator=True)
async def take_item(ctx, member: discord.Member, item_name: str, quantity: int = 1):
    if remove_from_inventory(member.id, item_name, quantity):
        await ctx.send(f'✅ У {member.mention} забрали {quantity} шт. **{item_name}**')
    else:
        await ctx.send(f'❌ У {member.mention} нет столько **{item_name}**')

@bot.command()
async def buy(ctx, *, item_name: str):
    item = get_item(item_name)
    if not item:
        await ctx.send(f'❌ Предмет **{item_name}** не найден.')
        return
    name, desc, price, role_id = item
    if get_balance(ctx.author.id) < price:
        await ctx.send(f'❌ Недостаточно денег. Нужно {price} монет.')
        return
    
    add_balance(ctx.author.id, -price)
    add_to_inventory(ctx.author.id, name)
    
    if role_id:
        role = ctx.guild.get_role(role_id)
        if role:
            await ctx.author.add_roles(role)
            await ctx.send(f'✅ Вы купили **{name}** и получили роль {role.mention}!')
        else:
            await ctx.send(f'✅ Вы купили **{name}**, но роль не найдена на сервере.')
    else:
        await ctx.send(f'✅ Вы купили **{name}** за {price} монет!')

@bot.command()
async def inv(ctx, member: discord.Member = None):
    member = member or ctx.author
    items = get_inventory(member.id)
    if not items:
        await ctx.send(f'У {member.mention} пустой инвентарь.')
        return
    embed = discord.Embed(title=f'🎒 Инвентарь {member.display_name}', color=0x00aaff)
    for item_name, quantity in items:
        embed.add_field(name=item_name, value=f'Количество: {quantity}', inline=False)
    embed.set_footer(text=f'Баланс: {get_balance(member.id)} монет')
    await ctx.send(embed=embed)

@bot.command()
async def shop(ctx):
    items = get_all_items()
    if not items:
        await ctx.send('🏪 Магазин пуст.')
        return
    embed = discord.Embed(title='🏪 Магазин', color=0xffaa00)
    for name, desc, price, role_id in items:
        role_text = f' (роль: <@&{role_id}>)' if role_id else ''
        embed.add_field(name=name, value=f'Цена: {price} монет{role_text}\n{desc[:50]}...', inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('❌ У вас нет прав для этой команды.')
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'❌ Не хватает аргументов. Используйте `!help {ctx.command.name}`')
    else:
        await ctx.send(f'❌ Ошибка: {str(error)}')
        print(error)

# === ЗАПУСК ===
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print('❌ Ошибка: DISCORD_TOKEN не найден в переменных окружения!')
    exit(1)

bot.run(TOKEN)