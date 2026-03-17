# app/services/sheets_service.py
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError # Import HttpError
from app.core.config import settings
from app.models.assistant_models import PortfolioAsset, OrderRequest # Import PortfolioAsset model
from typing import List, Dict, Any, Optional
import os
import asyncio # Required for run_in_executor
import functools # Required for run_in_executor partial
import traceback # Import traceback

# Scopes necesarios para acceder a Google Sheets y Drive
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly', # Solo lectura para portafolio
          'https://www.googleapis.com/auth/spreadsheets',           # Escritura para actualizar portafolio
          'https://www.googleapis.com/auth/drive.file']             # Para guardar/gestionar archivos si es necesario

class GoogleSheetsService:
    def __init__(self):
        self._creds = None
        self._service = None
        # TODO: Add configuration for Sheet Name and Range in settings
        self.sheet_name = "Portafolio" # Example default sheet name
        self.portfolio_range = "A:Z" # Example default range

    async def _get_credentials(self):
        """Carga y retorna las credenciales de servicio, ejecutando la carga en un thread."""
        if not self._creds:
            # Ensure the credentials file exists
            if not os.path.exists(settings.GOOGLE_API_CREDENTIALS_PATH):
                print(f"--- Error: Google API credentials file not found at {settings.GOOGLE_API_CREDENTIALS_PATH} ---")
                raise FileNotFoundError(f"Google API credentials file not found at {settings.GOOGLE_API_CREDENTIALS_PATH}")

            loop = asyncio.get_running_loop()
            try:
                 # Loading credentials can be synchronous, run in executor
                 self._creds = await loop.run_in_executor(None,
                     functools.partial(Credentials.from_service_account_file,
                                      settings.GOOGLE_API_CREDENTIALS_PATH, scopes=SCOPES)
                 )
                 print("--- Google API credentials loaded successfully. ---")
            except Exception as e:
                 print(f"--- Error loading Google credentials from {settings.GOOGLE_API_CREDENTIALS_PATH}: {e} ---")
                 traceback.print_exc()
                 raise # Re-raise the exception

        return self._creds

    async def _get_sheets_service(self):
        """Obtiene o construye el servicio de Google Sheets, ejecutando la construcción en un thread."""
        if not self._service:
            creds = await self._get_credentials()
            loop = asyncio.get_running_loop()
            try:
                # Building the service client can be synchronous, run in executor
                self._service = await loop.run_in_executor(None,
                    functools.partial(build, 'sheets', 'v4', credentials=creds)
                )
                print("--- Google Sheets service built successfully. ---")
            except Exception as e:
                print(f"--- Error building Google Sheets service: {e} ---")
                traceback.print_exc()
                raise # Re-raise the exception

        return self._service


    async def get_portfolio(self) -> List[PortfolioAsset]:
        """
        Lee los datos del portafolio desde Google Sheets y los valida/transforma
        al modelo Pydantic PortfolioAsset. Asume que la primera fila es el encabezado.
        """
        print(f"--- Attempting to fetch portfolio data from Sheet ID: {settings.GOOGLE_SHEET_ID}, Range: {self.sheet_name}!{self.portfolio_range} ---")
        service = await self._get_sheets_service()
        range_name = f'{self.sheet_name}!{self.portfolio_range}'

        # Execute the synchronous API call in a thread pool
        loop = asyncio.get_running_loop()
        try:
            get_values_sync = functools.partial(
                service.spreadsheets().values().get(
                    spreadsheetId=settings.GOOGLE_SHEET_ID, range=range_name).execute
            )
            result = await loop.run_in_executor(None, get_values_sync)
            values = result.get('values', [])

        except HttpError as err:
            print(f"--- Google Sheets API HTTP error fetching portfolio: {err} ---")
            traceback.print_exc()
            raise Exception(f"Error accessing Google Sheet {settings.GOOGLE_SHEET_ID}: {err}") # Re-raise as generic exception or custom one
        except Exception as e:
            print(f"--- Unexpected error fetching portfolio from Google Sheets: {e} ---")
            traceback.print_exc()
            raise Exception(f"Error fetching portfolio from Google Sheet {settings.GOOGLE_SHEET_ID}: {e}")


        if not values:
            print('--- No data found in Google Sheet portfolio. ---')
            return []
        else:
            # Assuming the first row is the header
            headers = [header.strip().lower().replace(" ", "_").replace("-", "_").replace(".", "") for header in values[0]] # Clean headers
            portfolio_list_validated: List[PortfolioAsset] = []
            print(f"--- Google Sheet Headers: {headers} ---")

            for row in values[1:]: # Process rows starting from the second one
                # Ensure row has same number of columns as headers, pad with None if shorter
                padded_row = row + [None] * (len(headers) - len(row))
                row_dict = dict(zip(headers, padded_row))

                try:
                    # --- Data Cleaning and Type Conversion ---
                    # Access values using cleaned header keys
                    # Convert relevant fields to float, handle potential errors
                    cantidad_str = row_dict.get("cantidad", "0").strip()
                    precio_compra_str = row_dict.get("precio_compra", "0").strip()
                    comisiones_str = row_dict.get("comisiones", "0").strip()
                    # Add other fields from your sheet that map to PortfolioAsset

                    # Attempt conversion, defaulting to 0.0 on error
                    cantidad = float(cantidad_str) if cantidad_str else 0.0
                    precio_compra = float(precio_compra_str) if precio_compra_str else 0.0
                    comisiones = float(comisiones_str) if comisiones_str else 0.0
                    # TODO: Convert other numeric/boolean fields

                    # Create Pydantic model instance
                    validated_item = PortfolioAsset(
                         activo=str(row_dict.get("activo", "")).strip(), # Ensure activo is string and stripped
                         cantidad=cantidad,
                         precio_compra=precio_compra,
                         comisiones=comisiones
                         # TODO: Add other fields from the model, using row_dict.get()
                    )
                    portfolio_list_validated.append(validated_item)
                    # print(f"--- Successfully validated row: {validated_item.dict()} ---") # Optional: Log each validated row
                except (ValueError, TypeError) as ve:
                     print(f"--- Skipping invalid portfolio row due to data conversion/validation error: {row} - Error: {ve} ---")
                     traceback.print_exc()
                except Exception as e:
                     print(f"--- Skipping invalid portfolio row due to unexpected error: {row} - Error: {e} ---")
                     traceback.print_exc()


            print(f"--- Successfully fetched and validated {len(portfolio_list_validated)} portfolio items. ---")
            return portfolio_list_validated


    async def update_portfolio(self, order_details: OrderRequest, order_result: Dict[str, Any]):
        """
        Updates the portafolio in Google Sheets after a successful order.
        The logic of how to update (sum/subtract quantity, calculate new average, add transaction row)
        depends heavily on the design of your spreadsheet.
        This is a complex operation that typically involves:
        1. Reading the current portfolio data.
        2. Finding the row for the specific asset.
        3. Calculating the new quantity, average cost, etc., based on the order details (buy/sell).
        4. Writing the updated row(s) back to the sheet.
        OR
        5. Appending a new transaction row to a log sheet, and having the portfolio sheet
           calculate balances automatically from the log (RECOMMENDED for robustness).
        """
        print(f"--- TODO: Implement update_portfolio for order: {order_details.dict()} with result: {order_result} ---")
        # This requires specific logic based on your Google Sheet's structure.
        # For example, if you have a transaction log sheet:
        # service = await self._get_sheets_service()
        # transaction_sheet_range = 'Transacciones!A:F' # Example range for a log sheet
        # new_row_data = [
        #     [
        #         str(datetime.now()), # Timestamp
        #         order_details.simbolo,
        #         order_details.tipo,
        #         order_details.cantidad,
        #         order_details.precio if order_details.precio is not None else "N/A",
        #         order_result.get("order_id", "") # Add order ID from IOL result
        #         # Add commission/fee if available
        #     ]
        # ]
        # body = { 'values': new_row_data }
        # try:
        #     append_sync = functools.partial(
        #         service.spreadsheets().values().append(
        #             spreadsheetId=settings.GOOGLE_SHEET_ID,
        #             range=transaction_sheet_range,
        #             valueInputOption='USER_ENTERED', # Use USER_ENTERED to preserve formatting/formulas
        #             insertDataOption='INSERT_ROWS',
        #             body=body
        #         ).execute
        #     )
        #     await loop.run_in_executor(None, append_sync)
        #     print("--- Transaction logged in Google Sheet. ---")
        # except HttpError as err:
        #     print(f"--- Google Sheets API HTTP error logging transaction: {err} ---")
        #     traceback.print_exc()
        #     # Decide how to handle - maybe just log, or raise a specific exception
        # except Exception as e:
        #     print(f"--- Unexpected error logging transaction to Google Sheets: {e} ---")
        #     traceback.print_exc()
        #     # Decide how to handle

        # If you are updating the main portfolio sheet directly (not recommended):
        # This is much more complex as it requires reading, modifying data structure in memory, and writing specific cells.
        # Example (pseudocode):
        # portfolio_data = await self.get_portfolio() # Get current data
        # # Find/update the specific asset in portfolio_data list
        # # Recalculate quantity, average cost, etc.
        # # Find the row index in the original sheet data
        # # Prepare values to write for that specific row
        # # Use service.spreadsheets().values().update with a specific range like 'Hoja1!A5:D5'

        print("--- Portfolio update logic placeholder executed. ---")
        pass # Placeholder implementation

    # TODO: Agregar métodos para guardar archivos en Google Drive si es necesario
