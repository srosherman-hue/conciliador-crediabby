import streamlit as st
import pandas as pd
import io

# Configuración básica de la página
st.set_page_config(page_title="Conciliación Multi-Tienda", page_icon="💸", layout="wide")

st.title("💸 Conciliador de Pagos: Banco vs Tiendas y App")

st.markdown('''
Sube todos los reportes. El sistema esperará hasta que presiones **Conciliar** para cruzar la información.
Visualizarás el resumen en pantalla y descargarás **un solo archivo del banco** con los colores correspondientes:
🟡 Crediabby | 🟢 Dominga Ortiz | 🟠 Ciudad Varyna | 🔵 Don Samuel
''')

# Inicializar el estado de sesión para guardar los resultados
if 'conciliacion_hecha' not in st.session_state:
    st.session_state['conciliacion_hecha'] = False

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
    
    # Buscar el encabezado de forma dinámica evaluando palabras clave de montos
    df_test = pd.read_excel(file, sheet_name=target_sheet, nrows=15, header=None)
    header_idx = 0
    for i, row in df_test.iterrows():
        row_strs = [str(x).lower().strip() for x in row.values if pd.notna(x)]
        if any(col in row_strs for col in ['monto bs.', 'monto (bs.)', 'monto bs. (bs.)', 'monto ($ usd)', 'monto usd ($)']):
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
            
    # ESTANDARIZACIÓN DE COLUMNAS (Soluciona el error de los cruces de otras tiendas)
    col_ref = find_column(df, 'n° referencia') or find_column(df, 'referencia') or find_column(df, 'ref')
    col_monto = find_column(df, 'monto bs') or find_column(df, 'bs') or find_column(df, 'monto')
    
    if col_ref: df['Ref_Standard'] = df[col_ref]
    if col_monto: df['Monto_Standard'] = df[col_monto]
    
    return df

# --- BOTÓN DE CONCILIACIÓN ---
archivos_app_cargados = [f for f in [app_file, dominga_file, varyna_file, samuel_file] if f is not None]

st.divider()

if banco_file and len(archivos_app_cargados) > 0:
    if st.button("🚀 INICIAR CONCILIACIÓN", type="primary", use_container_width=True):
        with st.spinner("Cruzando datos y aplicando colores a las filas..."):
            try:
                df_banco_original = load_banco_data(banco_file)
                
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

                # Limpiar Referencias de todos los archivos usando las columnas estandarizadas
                df_app_all['Referencia_str'] = df_app_all['Ref_Standard'].astype(str).str.strip()
                df_app_all['Referencia_str'] = df_app_all['Referencia_str'].str.replace('POS-PM-', '', regex=False)
                df_app_all['Referencia_str'] = df_app_all['Referencia_str'].str.extract(r'^([^\s\(]+)', expand=False)
                df_app_all['Referencia_str'] = df_app_all['Referencia_str'].str.replace('.0', '', regex=False)
                
                df_app_all['monto_num_str'] = df_app_all['Monto_Standard'].astype(str).str.replace(',', '.')
                df_app_all['monto_num'] = pd.to_numeric(df_app_all['monto_num_str'], errors='coerce').fillna(0)

                # --- Motor de Conciliación ---
                banco_matched_colors = {} 
                verificados = []
                solo_app = []
                
                for idx_app, row_app in df_app_all.iterrows():
                    ref_app = str(row_app['Referencia_str']).strip()
                    if ref_app.lower() in ['nan', 'none', 'nat', ''] or pd.isna(row_app['Referencia_str']):
                        continue
                    
                    monto_app = row_app['monto_num']
                    color_origen = row_app['Color_Asignado']
                    origen_str = row_app['Origen_Archivo']
                    
                    posibles_matches = df_banco_ingresos[
                        df_banco_ingresos['referencia_str'].str.endswith(ref_app) & 
                        (~df_banco_ingresos.index.isin(banco_matched_colors.keys()))
                    ]
                    
                    match_found = False
                    if not posibles_matches.empty:
                        for idx_banco, match_banco in posibles_matches.iterrows():
                            monto_banco = match_banco['monto_num']
                            if abs(monto_app - monto_banco) <= 1.0:
                                banco_matched_colors[idx_banco] = color_origen 
                                verificados.append({
                                    'Tienda/App': origen_str,
                                    'Referencia': ref_app,
                                    'Monto': monto_app,
                                    'Estado': 'Verificado'
                                })
                                match_found = True
                                break 
                                
                    if not match_found:
                        solo_app.append({
                            'Tienda/App': origen_str,
                            'Referencia': ref_app,
                            'Monto': monto_app,
                            'Estado': 'Falta en Banco'
                        })
                
                df_solo_banco = df_banco_ingresos[~df_banco_ingresos.index.isin(banco_matched_colors.keys())].copy()
                df_solo_banco['Estado'] = 'Falta en App/Tiendas'
                
                # --- Generar Archivo Excel Pintado ---
                def pintar_filas(row):
                    color_hex = banco_matched_colors.get(row.name, '')
                    style = f'background-color: {color_hex}' if color_hex else ''
                    return [style] * len(row)
                
                df_banco_export = df_banco_original.copy()
                df_banco_export.columns = df_banco_original.attrs.get('columnas_originales', df_banco_original.columns)
                styled_banco = df_banco_export.style.apply(pintar_filas, axis=1)
                
                output_excel = io.BytesIO()
                with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                    styled_banco.to_excel(writer, index=False, sheet_name='Banco_Conciliado')
                
                # Guardar en Session State para que no se borre al recargar la web
                st.session_state['conciliacion_hecha'] = True
                st.session_state['excel_data'] = output_excel.getvalue()
                st.session_state['df_verificados'] = pd.DataFrame(verificados)
                st.session_state['df_solo_app'] = pd.DataFrame(solo_app)
                st.session_state['df_solo_banco'] = df_solo_banco
                
            except Exception as e:
                st.error(f"Ocurrió un error: {e}")

# --- MOSTRAR RESULTADOS SI LA CONCILIACIÓN FUE EXITOSA ---
if st.session_state.get('conciliacion_hecha'):
    st.success("✅ ¡Conciliación terminada! Revisa el resumen y descarga el archivo Excel.")
    
    df_ver = st.session_state['df_verificados']
    df_app = st.session_state['df_solo_app']
    df_banco = st.session_state['df_solo_banco']
    
    # 1. Cuadro de Resumen Visual en la Web
    c1, c2, c3 = st.columns(3)
    c1.metric("✅ Verificados (Conciliados)", len(df_ver))
    c2.metric("❌ Faltan en Banco (Solo en App)", len(df_app))
    c3.metric("⚠️ Sobran en Banco (No identificados)", len(df_banco))
    
    tab1, tab2, tab3 = st.tabs(["✅ Verificados", "❌ Faltan en Banco", "⚠️ Sobran en Banco"])
    with tab1: st.dataframe(df_ver, use_container_width=True)
    with tab2: st.dataframe(df_app, use_container_width=True)
    with tab3: st.dataframe(df_banco, use_container_width=True)
    
    st.divider()
    
    # 2. Único Botón de Descarga (Excel con colores)
    st.download_button(
        label="⬇️ DESCARGAR BANCO MARCADO (EXCEL)",
        data=st.session_state['excel_data'],
        file_name="Banco_Conciliado_Multicolor.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True
    )