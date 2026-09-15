import streamlit as st
import pandas as pd
import io

# Configuración básica de la página
st.set_page_config(page_title="Conciliación Multi-Tienda", page_icon="💸", layout="wide")

st.title("💸 Conciliador de Pagos: Banco vs Tiendas y App")

st.markdown('''
Sube todos los reportes. El sistema esperará hasta que presiones **Conciliar** para cruzar la información.
Al finalizar, descargarás **un solo archivo del banco** con los colores correspondientes:
🟡 Crediabby | 🟢 Dominga Ortiz | 🟠 Ciudad Varyna | 🔵 Don Samuel
''')

# Inicializar el estado de sesión para guardar el archivo y que no se borre al hacer clic
if 'excel_data' not in st.session_state:
    st.session_state['excel_data'] = None
    st.session_state['resumen'] = None

# --- SECCIÓN DE SUBIDA DE ARCHIVOS ---
st.subheader("1. Archivos Requeridos")
banco_file = st.file_uploader("🏦 Sube el archivo del Banco de Venezuela", type=["xlsx", "xls", "csv"], key="banco")

col1, col2 = st.columns(2)
with col1:
    app_file = st.file_uploader("🟡 Sube Crediabby (App)", type=["xlsx", "xls", "csv"], key="app")
    dominga_file = st.file_uploader("🟢 Sube Dominga Ortiz", type=["xlsx", "xls", "csv"], key="dominga")
with col2:
    varyna_file = st.file_uploader("🟠 Sube Ciudad Varyna", type=["xlsx", "xls", "csv"], key="varyna")
    samuel_file = st.file_uploader("🔵 Sube Don Samuel", type=["xlsx", "xls", "csv"], key="samuel")

# --- FUNCIONES AUXILIARES ---
def find_column(df, keyword):
    keyword = keyword.lower().strip()
    for col in df.columns:
        col_str = str(col).lower().strip()
        if keyword in col_str:
            return col
    return None

def parse_monto_banco(val):
    if pd.isna(val): return 0.0
    val_str = str(val).strip().replace('.', '').replace(',', '.')
    try: return float(val_str)
    except: return 0.0

def load_banco_data(file):
    file.seek(0)
    if file.name.lower().endswith('.csv'):
        df = pd.read_csv(file)
        if len(df.columns) <= 1:
            file.seek(0)
            df = pd.read_csv(file, sep=';')
    else:
        df = pd.read_excel(file)
        
    if df.empty or len(df.columns) == 0:
        return None
        
    columnas_originales = df.columns.tolist()
    df.attrs['columnas_originales'] = columnas_originales
    df.columns = df.columns.astype(str).str.strip().str.lower()
    return df

def load_app_data(file, is_crediabby):
    file.seek(0)
    xl = pd.ExcelFile(file)
    target_sheet = xl.sheet_names[1] if len(xl.sheet_names) > 1 else xl.sheet_names[0]
    
    # Buscar el encabezado de forma dinámica bajando fila por fila hasta encontrar "referencia"
    df_test = pd.read_excel(file, sheet_name=target_sheet, nrows=15, header=None)
    header_idx = 0
    for i, row in df_test.iterrows():
        row_strs = [str(x).lower() for x in row.values]
        if any('referencia' in s for s in row_strs) or any('monto' in s for s in row_strs):
            header_idx = i
            break
            
    df = pd.read_excel(file, sheet_name=target_sheet, header=header_idx)
    df.columns = df.columns.astype(str).str.strip().str.lower()
    
    # Filtro exclusivo de Pago Móvil para las sucursales físicas
    if not is_crediabby:
        col_metodo = find_column(df, 'método de pago') or find_column(df, 'metodo')
        if col_metodo:
            mask = df[col_metodo].astype(str).str.lower().str.contains('pago m', na=False)
            df = df[mask].copy()
    
    return df

# --- BOTÓN DE CONCILIACIÓN ---
archivos_app_cargados = [f for f in [app_file, dominga_file, varyna_file, samuel_file] if f is not None]

st.divider()

if banco_file and len(archivos_app_cargados) > 0:
    if len(archivos_app_cargados) < 4:
        st.info("💡 Tienes archivos de tiendas pendientes por subir, pero puedes conciliar con los que tienes actualmente.")
        
    if st.button("🚀 INICIAR CONCILIACIÓN", type="primary", use_container_width=True):
        with st.spinner("Cruzando datos y aplicando colores a las filas..."):
            try:
                df_banco_original = load_banco_data(banco_file)
                
                if df_banco_original is None:
                    st.error("❌ El archivo del banco está vacío o no se pudo leer.")
                    st.stop()
                    
                col_ref_banco = find_column(df_banco_original, 'referencia') or find_column(df_banco_original, 'ref')
                col_monto_banco = find_column(df_banco_original, 'monto')
                col_tipo_banco = find_column(df_banco_original, 'tipomovimiento') or find_column(df_banco_original, 'concepto')

                # Limpiar Banco (Filtramos solo ingresos/créditos)
                if col_tipo_banco:
                    df_banco_ingresos = df_banco_original[df_banco_original[col_tipo_banco].astype(str).str.contains('Crédito', case=False, na=False)].copy()
                else:
                    df_banco_ingresos = df_banco_original[~df_banco_original[col_monto_banco].astype(str).str.contains('-')].copy()
                    
                df_banco_ingresos['monto_num'] = df_banco_ingresos[col_monto_banco].apply(parse_monto_banco)
                df_banco_ingresos['referencia_str'] = df_banco_ingresos[col_ref_banco].astype(str).str.strip().str.replace('.0', '', regex=False)

                # Procesar Tiendas
                dfs_app = []
                # (Archivo, Origen, Color_Hexadecimal, es_crediabby)
                configs = [
                    (app_file, 'Crediabby', '#FFFF99', True),          # Amarillo pastel
                    (dominga_file, 'Dominga Ortiz', '#90EE90', False), # Verde pastel
                    (varyna_file, 'Ciudad Varyna', '#FFA500', False),  # Naranja
                    (samuel_file, 'Don Samuel', '#ADD8E6', False)      # Azul pastel
                ]
                
                for file_obj, origen, color, is_crediabby in configs:
                    if file_obj is not None:
                        df = load_app_data(file_obj, is_crediabby)
                        if df is not None and not df.empty:
                            df['Origen_Archivo'] = origen
                            df['Color_Asignado'] = color
                            dfs_app.append(df)
                
                if not dfs_app:
                    st.error("❌ No se encontraron datos válidos (o pagos móviles) en las tiendas subidas.")
                    st.stop()
                    
                df_app_all = pd.concat(dfs_app, ignore_index=True)

                col_ref_app = find_column(df_app_all, 'n° referencia') or find_column(df_app_all, 'referencia') or find_column(df_app_all, 'ref')
                col_monto_app = find_column(df_app_all, 'monto bs') or find_column(df_app_all, 'bs') or find_column(df_app_all, 'monto')

                # Limpiar Referencias de todos los archivos (App y Sucursales)
                df_app_all['Referencia_str'] = df_app_all[col_ref_app].astype(str).str.strip()
                df_app_all['Referencia_str'] = df_app_all['Referencia_str'].str.replace('POS-PM-', '', regex=False)
                df_app_all['Referencia_str'] = df_app_all['Referencia_str'].str.extract(r'^([^\s\(]+)', expand=False)
                df_app_all['Referencia_str'] = df_app_all['Referencia_str'].str.replace('.0', '', regex=False)
                
                df_app_all['monto_num_str'] = df_app_all[col_monto_app].astype(str).str.replace(',', '.')
                df_app_all['monto_num'] = pd.to_numeric(df_app_all['monto_num_str'], errors='coerce').fillna(0)

                # --- Motor de Conciliación ---
                banco_matched_colors = {} 
                total_verificados = 0
                
                for idx_app, row_app in df_app_all.iterrows():
                    ref_app = str(row_app['Referencia_str']).strip()
                    if ref_app.lower() in ['nan', 'none', 'nat', ''] or pd.isna(row_app['Referencia_str']):
                        continue
                    
                    monto_app = row_app['monto_num']
                    color_origen = row_app['Color_Asignado']
                    
                    posibles_matches = df_banco_ingresos[
                        df_banco_ingresos['referencia_str'].str.endswith(ref_app) & 
                        (~df_banco_ingresos.index.isin(banco_matched_colors.keys()))
                    ]
                    
                    if not posibles_matches.empty:
                        for idx_banco, match_banco in posibles_matches.iterrows():
                            monto_banco = match_banco['monto_num']
                            if abs(monto_app - monto_banco) <= 1.0:
                                # Aquí es donde se le dice a la fila del banco de qué color debe pintarse
                                banco_matched_colors[idx_banco] = color_origen 
                                total_verificados += 1
                                break 
                
                # --- Generar Archivo Excel Pintado ---
                def pintar_filas(row):
                    # Asignamos el color dictado por la conciliación, si no cruzó, queda vacío ('')
                    color_hex = banco_matched_colors.get(row.name, '')
                    style = f'background-color: {color_hex}' if color_hex else ''
                    return [style] * len(row)
                
                df_banco_export = df_banco_original.copy()
                df_banco_export.columns = df_banco_original.attrs.get('columnas_originales', df_banco_original.columns)
                styled_banco = df_banco_export.style.apply(pintar_filas, axis=1)
                
                output_excel = io.BytesIO()
                with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                    styled_banco.to_excel(writer, index=False, sheet_name='Banco_Conciliado')
                
                # Guardamos en la memoria temporal de Streamlit
                st.session_state['excel_data'] = output_excel.getvalue()
                st.session_state['resumen'] = {
                    'verificados': total_verificados,
                    'pendientes_banco': len(df_banco_ingresos) - total_verificados
                }
                
            except Exception as e:
                import traceback
                st.error(f"Ocurrió un error: {e}")
                st.write(traceback.format_exc())

# --- MOSTRAR EL ÚNICO BOTÓN DE DESCARGA SI YA SE CONCILIÓ ---
if st.session_state.get('excel_data') is not None:
    st.success("✅ Conciliación terminada. El archivo ya tiene los colores correspondientes de las 4 sucursales aplicados.")
    
    res = st.session_state['resumen']
    st.write(f"📊 **Resumen:** Se cruzaron **{res['verificados']}** pagos. Quedaron **{res['pendientes_banco']}** depósitos en el banco sin identificar.")
    
    st.download_button(
        label="⬇️ DESCARGAR ARCHIVO DEL BANCO CONCILIADO (EXCEL)",
        data=st.session_state['excel_data'],
        file_name="Banco_Conciliado_Multicolor.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True
    )