import os
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

# Cargar variables de entorno
load_dotenv(".env")

BULLMARKET_EMAIL = os.getenv("BULLMARKET_EMAIL")
BULLMARKET_PASSWORD = os.getenv("BULLMARKET_PASSWORD")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")  # Ajusta si es necesario

# Inicializar navegador
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_argument("--disable-notifications")
driver = webdriver.Chrome(executable_path=CHROMEDRIVER_PATH, options=options)

# Abrir BullMarket
driver.get("https://www.bullmarketbrokers.com/Login")

# Ingresar email
email_input = driver.find_element(By.ID, "Email")  # Asegúrate de que el ID sea correcto
email_input.send_keys(BULLMARKET_EMAIL)

# Ingresar contraseña
password_input = driver.find_element(By.ID, "Password")  # Asegúrate de que el ID sea correcto
password_input.send_keys(BULLMARKET_PASSWORD)
password_input.send_keys(Keys.RETURN)

# Esperar que el usuario ingrese manualmente el código de confirmación 2FA
print("Por favor, ingresa el código de confirmación manualmente en la web y presiona Enter aquí...")
input()

# Ahora la sesión está activa, puedes continuar con scraping o automatización
print("Login completado con éxito.")

# Ejemplo: obtener nombre de usuario de la cuenta
# user_name = driver.find_element(By.CSS_SELECTOR, ".user-name-selector").text
# print(f"Usuario logueado: {user_name}")

# Mantener la ventana abierta (opcional)
time.sleep(10)

# Cerrar navegador
driver.quit()
