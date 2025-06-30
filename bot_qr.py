import os
import io
import asyncio
import qrcode
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from PIL import Image, ImageDraw
import logging

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuración por defecto
DEFAULT_QR_CONFIG = {
    'color': 'black',
    'background': 'white',
    'size': 10
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    🤖 Bot Generador de Códigos QR Personalizados
    
    Comandos disponibles:
    /start - Muestra este mensaje
    /setlogo - Activa el modo de configuración de logo
    /qr <url> [color] [fondo] [tamaño] - Genera un QR personalizado
    /clearlogo - Elimina tu logo configurado
    
    📋 Cómo configurar tu logo:
    1. Escribe /setlogo
    2. En el siguiente mensaje, envía tu imagen
    
    Ejemplos de QR:
    /qr https://ejemplo.com
    /qr https://ejemplo.com #FF0000 white 15
    """
    await update.message.reply_text(help_text)

async def set_logo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activa el modo de configuración de logo"""
    try:
        # Marcar que el usuario está configurando logo
        context.user_data['setting_logo'] = True
        
        await update.message.reply_text(
            "📷 **Modo configuración de logo activado**\n\n"
            "Ahora envía tu imagen en el siguiente mensaje.\n\n"
            "Recomendaciones:\n"
            "• Formato: PNG, JPG, JPEG\n"
            "• Tamaño: Máximo 5MB\n"
            "• Forma: Preferiblemente cuadrada\n"
            "• Fondo transparente (PNG) se ve mejor\n\n"
            "Para cancelar, usa /start",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error en set_logo: {e}")
        await update.message.reply_text("⚠️ Error al activar modo logo.")

async def clear_logo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina el logo del usuario"""
    try:
        user_id = update.message.from_user.id
        logo_path = f"user_logos/logo_{user_id}.png"
        
        # Eliminar archivo si existe
        if os.path.exists(logo_path):
            os.remove(logo_path)
        
        # Limpiar datos del usuario
        context.user_data.pop('logo_path', None)
        context.user_data.pop('setting_logo', None)
        
        await update.message.reply_text("🗑️ Logo eliminado correctamente.")
        
    except Exception as e:
        logger.error(f"Error en clear_logo: {e}")
        await update.message.reply_text("⚠️ Error al eliminar logo.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las fotos enviadas por el usuario"""
    try:
        # Verificar si el usuario está configurando logo
        if not context.user_data.get('setting_logo', False):
            await update.message.reply_text(
                "ℹ️ Si quieres configurar un logo, primero usa /setlogo"
            )
            return

        # Verificar que sea una foto
        if not update.message.photo:
            await update.message.reply_text(
                "⚠️ Por favor envía una imagen válida."
            )
            return

        # Crear directorio si no existe
        os.makedirs("user_logos", exist_ok=True)
        
        user_id = update.message.from_user.id
        logo_path = f"user_logos/logo_{user_id}.png"
        
        await update.message.reply_text("⏳ Procesando tu imagen...")
        
        # Descargar la foto (usamos la de mayor calidad)
        photo_file = await update.message.photo[-1].get_file()
        
        # Verificar tamaño del archivo
        if photo_file.file_size > 5 * 1024 * 1024:  # 5MB
            await update.message.reply_text(
                "📏 La imagen es demasiado grande. Máximo 5MB."
            )
            return
        
        # Proceso de descarga con timeout
        try:
            await asyncio.wait_for(
                photo_file.download_to_drive(logo_path),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            await update.message.reply_text(
                "⌛ La descarga tardó demasiado. Intenta con una imagen más pequeña."
            )
            return

        # Procesar la imagen
        try:
            with Image.open(logo_path) as img:
                original_size = img.size
                
                # Redimensionar manteniendo relación de aspecto
                max_size = 400
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # Convertir a RGBA para manejar transparencia
                if img.mode in ('RGBA', 'LA'):
                    # Mantener transparencia
                    background = Image.new('RGBA', img.size, (255, 255, 255, 0))
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                elif img.mode != 'RGB':
                    # Convertir otros modos a RGB
                    img = img.convert('RGB')
                
                # Guardar como PNG (mantiene transparencia)
                img.save(logo_path, 'PNG', optimize=True)
                
                # Guardar referencia para el usuario
                context.user_data['logo_path'] = logo_path
                context.user_data['setting_logo'] = False  # Desactivar modo configuración
                
                await update.message.reply_text(
                    "✅ **¡Logo configurado correctamente!**\n\n"
                    f"📁 Archivo guardado\n"
                    f"📐 Tamaño original: {original_size[0]}x{original_size[1]}px\n"
                    f"📐 Tamaño procesado: {img.size[0]}x{img.size[1]}px\n\n"
                    "Ahora usa `/qr <url>` para generar tu código QR personalizado.\n"
                    "Usa `/clearlogo` si quieres eliminarlo.",
                    parse_mode='Markdown'
                )
                
        except Exception as img_error:
            logger.error(f"Error procesando imagen: {img_error}")
            if os.path.exists(logo_path):
                os.remove(logo_path)
            await update.message.reply_text(
                "❌ No pude procesar esa imagen.\n"
                "Formatos soportados: JPG, JPEG, PNG, GIF\n"
                "Intenta con otra imagen."
            )

    except Exception as e:
        logger.error(f"Error en handle_photo: {e}")
        # Limpiar estado en caso de error
        context.user_data.pop('setting_logo', None)
        await update.message.reply_text(
            "⚠️ Ocurrió un error inesperado. Usa /setlogo para intentar de nuevo."
        )

def generate_qr(url, color='black', background='white', size=10, logo_path=None):
    """Genera un código QR con opciones de personalización"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=size,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color=color, back_color=background).convert('RGB')
        
        # Añadir logo si existe
        if logo_path and os.path.exists(logo_path):
            try:
                with Image.open(logo_path) as logo:
                    # Tamaño del logo (15% del QR para mejor legibilidad)
                    qr_size = min(img.size)
                    logo_size = qr_size // 7  # Más pequeño para mejor escaneo
                    
                    # Redimensionar logo manteniendo aspecto
                    logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
                    
                    # Crear una máscara circular para el logo (opcional)
                    mask = Image.new('L', logo.size, 0)
                    draw = ImageDraw.Draw(mask)
                    draw.ellipse((0, 0) + logo.size, fill=255)
                    
                    # Posición centrada
                    position = (
                        (img.size[0] - logo.size[0]) // 2,
                        (img.size[1] - logo.size[1]) // 2
                    )
                    
                    # Crear fondo blanco para el logo
                    logo_bg = Image.new('RGB', logo.size, 'white')
                    img.paste(logo_bg, position)
                    
                    # Pegar logo
                    if logo.mode == 'RGBA':
                        img.paste(logo, position, logo)
                    else:
                        img.paste(logo, position)
                    
            except Exception as e:
                logger.error(f"Error añadiendo logo: {e}")
        
        # Guardar en memoria
        bio = io.BytesIO()
        bio.name = 'qr_code.png'
        img.save(bio, 'PNG', optimize=True)
        bio.seek(0)
        return bio
        
    except Exception as e:
        logger.error(f"Error generando QR: {e}")
        raise

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if not args:
            await update.message.reply_text(
                "ℹ️ **Uso:** `/qr <url> [color] [fondo] [tamaño]`\n\n"
                "**Ejemplos:**\n"
                "• `/qr https://google.com`\n"
                "• `/qr https://github.com blue white 12`\n"
                "• `/qr https://example.com #FF0000 #00FF00 15`\n\n"
                "**Colores:** black, white, red, blue, green, #FF0000, etc.\n"
                "**Tamaño:** 5-20",
                parse_mode='Markdown'
            )
            return

        url = args[0]
        
        # Validar URL
        if not url.startswith(('http://', 'https://')):
            # Intentar agregar https:// automáticamente
            if '.' in url and not url.startswith(('ftp://', 'file://')):
                url = 'https://' + url
            else:
                await update.message.reply_text("🔒 La URL debe comenzar con http:// o https://")
                return

        # Configuración personalizada
        config = DEFAULT_QR_CONFIG.copy()
        if len(args) > 1: config['color'] = args[1]
        if len(args) > 2: config['background'] = args[2]
        if len(args) > 3:
            try:
                config['size'] = int(args[3])
                if not (5 <= config['size'] <= 20):
                    await update.message.reply_text("📏 El tamaño debe ser entre 5 y 20")
                    return
            except ValueError:
                await update.message.reply_text("🔢 El tamaño debe ser un número")
                return

        # Obtener logo del usuario si existe
        logo_path = context.user_data.get('logo_path')
        
        await update.message.reply_text("⏳ Generando tu QR personalizado...")
        
        # Generar QR
        qr_img = generate_qr(
            url=url,
            color=config['color'],
            background=config['background'],
            size=config['size'],
            logo_path=logo_path
        )
        
        # Preparar caption
        caption = (
            f"🔗 **URL:** {url}\n"
            f"🎨 **Color:** {config['color']} | **Fondo:** {config['background']} | **Tamaño:** {config['size']}\n"
        )
        
        if logo_path and os.path.exists(logo_path):
            caption += "🖼️ **Logo:** Incluido"
        else:
            caption += "💡 **Tip:** Usa /setlogo para añadir tu logo"
        
        # Enviar resultado
        await update.message.reply_photo(
            photo=qr_img,
            caption=caption,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error en qr_command: {e}")
        await update.message.reply_text("⚠️ Error al generar el QR. Intenta nuevamente.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja mensajes de texto que no son comandos"""
    text = update.message.text
    
    # Si el usuario está configurando logo, recordarle que necesita enviar imagen
    if context.user_data.get('setting_logo', False):
        await update.message.reply_text(
            "📷 Esperando tu imagen para configurar como logo.\n"
            "Envía una foto en el siguiente mensaje o usa /start para cancelar."
        )
        return
    
    # Auto-generar QR para URLs
    if text and (text.startswith(('http://', 'https://')) or ('.' in text and len(text.split('.')) >= 2)):
        try:
            # Agregar https:// si no tiene protocolo
            if not text.startswith(('http://', 'https://')):
                text = 'https://' + text
                
            qr_img = generate_qr(text)
            await update.message.reply_photo(
                photo=qr_img,
                caption=f"📲 **QR generado automáticamente**\n🔗 {text}\n\n💡 Usa `/qr {text}` para personalizarlo",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error en auto-QR: {e}")
            await update.message.reply_text(f"⚠️ Error al generar QR automático para: {text}")

def main():
    # Configuración del bot
    TOKEN = "TU_TOKEN_AQUI"  # Reemplaza con tu token real
    
    if TOKEN == "TU_TOKEN_AQUI":
        print("❌ ERROR: Debes configurar tu TOKEN de bot de Telegram")
        print("1. Habla con @BotFather en Telegram")
        print("2. Crea un nuevo bot con /newbot")
        print("3. Copia el token y reemplázalo en TOKEN")
        return
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setlogo", set_logo))
    app.add_handler(CommandHandler("clearlogo", clear_logo))
    app.add_handler(CommandHandler("qr", qr_command))
    
    # Handler para fotos (debe ir antes del handler de texto)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Handler para texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Iniciar bot
    logger.info("🤖 Bot iniciado correctamente...")
    print("🚀 Bot QR ejecutándose...")
    print("📱 Prueba con /start en Telegram")
    
    try:
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        logger.info("🛑 Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"💥 Error crítico: {e}")

if __name__ == '__main__':
    main()
