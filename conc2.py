import streamlit as st
import pandas as pd
import io

# Configuración básica de la página
st.set_page_config(page_title="Conciliación Multi-Tienda", page_icon="💸", layout="wide")

st.title("💸 Conciliador de Pagos: Banco vs Tiendas y App")

st.markdown('''
Sube el reporte del banco y los de cada sucursal/app. El sistema cruzará las referencias de **Pago Móvil** y asignará un color en el archivo final según la tienda de origen.
''')

# --- SECCIÓN DE SUBIDA DE ARCHIVOS ---
st.subheader("🏦 1. Archivo del Banco")
banco_file = st.file_uploader("📂 Sube el archivo del Banco de Venezuela", type=["xlsx", "xls", "csv"], key="banco")

st.subheader("🏪 2. Reportes de Tiendas y App")
col1, col2 = st.columns(2)
with col1:
    app_file = st.file_uploader("🟡 Sube el reporte de Crediabby (App)", type=["xlsx", "xls", "csv"], key="app")
    dominga_file = st.file_uploader("🟢 Sube el reporte de Dominga Ortiz", type=["xlsx", "xls", "csv"], key="dominga")
with col2:
    varyna_file = st.file_uploader("🟠 Sube el reporte de Ciudad Varyna", type=["xlsx", "xls", "csv"], key="varyna")
    samuel_file = st.file_uploader("🔵 Sube el reporte de Don Samuel", type=["xlsx", "xls", "csv"], key="samuel")

# Función auxiliar para buscar columnas por nombre
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
    # Selecciona la segunda hoja (índice 1) si existe, de lo contrario la primera
    target_sheet = xl.sheet_names[1] if len(xl.sheet_names) > 1 else xl.sheet_names[0]
    
    # Buscar dinámicamente la fila de encabezado leyendo las primeras filas
    df_test = pd.read_excel(file, sheet_name=target_sheet, nrows=15)
    header_idx = 0
    for i, row in df_test.iterrows():
        row_strs = [str(x).lower() for x in row.values]
        if any('referencia' in s for s in row_strs) or any('monto' in s for s in row_strs):
            header_idx = i + 1
            break
            
    df = pd.read_excel(file, sheet_name=target_sheet, header=header_idx)
    df.columns = df.columns.astype(str).str.strip().str.lower()
    
    # Si NO es Crediabby, filtramos exclusivamente 'Pago Móvil'
    if not is_crediabby:
        col_metodo = find_column(df, 'método de pago') or find_column(df, 'metodo de pago') or find_column(df, 'método')
        if col_metodo:
            mask = df[col_metodo].astype(str).str.lower().str.contains('pago m', na=False)
            df = df[mask].copy()
    
    return df

# --- LÓGICA PRINCIPAL ---
archivos_app_cargados = [f for f in [app_file, dominga_file, varyna_file, samuel_file] if f is not None]

if banco_file and archivos_app_cargados:
    with st.spinner("Procesando y cruzando información..."):
        try:
            df_banco_original = load_banco_data(banco_file)
            
            if df_banco_original is None:
                st.error("❌ El archivo del banco está vacío o no se pudo leer.")
                st.stop()
                
            # Validar columnas del banco
            col_ref_banco = find_column(df_banco_original, 'referencia') or find_column(df_banco_original, 'ref')
            col_monto_banco = find_column(df_banco_original, 'monto')
            col_tipo_banco = find_column(df_banco_original, 'tipomovimiento') or find_column(df_banco_original, 'concepto')
            col_fecha_banco = find_column(df_banco_original, 'fecha')

            if not col_ref_banco or not col_monto_banco:
                st.error("❌ No se encontraron las columnas de Referencia o Monto en el archivo del **Banco**.")
                st.stop()
                
            # Limpiar Banco
            if col_tipo_banco:
                df_banco_ingresos = df_banco_original[df_banco_original[col_tipo_banco].astype(str).str.contains('Crédito', case=False, na=False)].copy()
            else:
                df_banco_ingresos = df_banco_original[~df_banco_original[col_monto_banco].astype(str).str.contains('-')].copy()
                
            df_banco_ingresos['monto_num'] = df_banco_ingresos[col_monto_banco].apply(parse_monto_banco)
            df_banco_ingresos['referencia_str'] = df_banco_ingresos[col_ref_banco].astype(str).str.strip().str.replace('.0', '', regex=False)

            # Procesar todos los archivos de tiendas/app
            dfs_app = []
            
            # (Archivo, Origen, Color_Hexadecimal_Pastel, es_crediabby)
            configs = [
                (app_file, 'Crediabby', '#FFFF99', True),      # Amarillo
                (dominga_file, 'Dominga Ortiz', '#A9DFBF', False), # Verde
                (varyna_file, 'Ciudad Varyna', '#F5B041', False),  # Naranja
                (samuel_file, 'Don Samuel', '#AED6F1', False)      # Azul
            ]
            
            for file_obj, origen, color, is_crediabby in configs:
                if file_obj is not None:
                    df = load_app_data(file_obj, is_crediabby)
                    if df is not None and not df.empty:
                        df['Origen_Archivo'] = origen
                        df['Color_Asignado'] = color
                        dfs_app.append(df)
            
            if not dfs_app:
                st.error("❌ No se encontraron datos válidos (o pagos móviles) en los archivos de tiendas/app subidos.")
                st.stop()
                
            # Unimos los 4 archivos en uno solo
            df_app_all = pd.concat(dfs_app, ignore_index=True)

            # Buscar columnas estándar en el dataframe combinado
            col_ref_app = find_column(df_app_all, 'n° referencia') or find_column(df_app_all, 'referencia') or find_column(df_app_all, 'ref')
            col_monto_app = find_column(df_app_all, 'monto bs') or find_column(df_app_all, 'bs') or find_column(df_app_all, 'monto')

            if not col_ref_app or not col_monto_app:
                st.error("❌ No se encontraron las columnas de Referencia o Monto en los archivos de Tiendas/App.")
                st.stop()

            # Limpieza de referencias
            df_app_all['Referencia_str'] = df_app_all[col_ref_app].astype(str).str.strip()
            df_app_all['Referencia_str'] = df_app_all['Referencia_str'].str.replace('POS-PM-', '', regex=False)
            df_app_all['Referencia_str'] = df_app_all['Referencia_str'].str.extract(r'^([^\s\(]+)', expand=False)
            df_app_all['Referencia_str'] = df_app_all['Referencia_str'].str.replace('.0', '', regex=False)
            
            df_app_all['monto_num_str'] = df_app_all[col_monto_app].astype(str).str.replace(',', '.')
            df_app_all['monto_num'] = pd.to_numeric(df_app_all['monto_num_str'], errors='coerce').fillna(0)

            # --- Motor de Conciliación ---
            verificados = []
            solo_app = []
            # Diccionario para saber qué color le toca a cada fila del banco
            banco_matched_colors = {} 
            
            for idx_app, row_app in df_app_all.iterrows():
                ref_app = str(row_app['Referencia_str']).strip()
                if ref_app.lower() in ['nan', 'none', 'nat', ''] or pd.isna(row_app['Referencia_str']):
                    continue
                
                monto_app = row_app['monto_num']
                color_origen = row_app['Color_Asignado']
                origen_str = row_app['Origen_Archivo']
                
                # Buscamos en el banco
                posibles_matches = df_banco_ingresos[
                    df_banco_ingresos['referencia_str'].str.endswith(ref_app) & 
                    (~df_banco_ingresos.index.isin(banco_matched_colors.keys()))
                ]
                
                match_found = False
                if not posibles_matches.empty:
                    for idx_banco, match_banco in posibles_matches.iterrows():
                        monto_banco = match_banco['monto_num']
                        if abs(monto_app - monto_banco) <= 1.0:
                            # ¡Match! Asignamos el color correcto según la tienda
                            banco_matched_colors[idx_banco] = color_origen 
                            verificados.append({
                                'Tienda/App': origen_str,
                                **row_app.to_dict(), 
                                'Ref Banco': match_banco['referencia_str'], 
                                'Monto Banco': monto_banco, 
                                'Estado': 'Verificado'
                            })
                            match_found = True
                            break 
                
                if not match_found:
                    row_dict = row_app.to_dict()
                    row_dict['Tienda/App'] = origen_str
                    row_dict['Estado'] = 'Falta en Banco'
                    solo_app.append(row_dict)
                    
            df_solo_banco = df_banco_ingresos[~df_banco_ingresos.index.isin(banco_matched_colors.keys())].copy()
            df_solo_banco['Estado'] = 'Falta en App/Tiendas'
            
            df_verificados = pd.DataFrame(verificados)
            df_solo_app = pd.DataFrame(solo_app)

            # --- Interfaz de Resultados ---
            st.divider()
            st.subheader("📊 Resumen de la Conciliación Multi-Tienda")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("✅ Verificados", len(df_verificados))
            c2.metric("❌ Faltan en Banco", len(df_solo_app))
            c3.metric("⚠️ Sobran en Banco", len(df_solo_banco))
            
            tab1, tab2, tab3 = st.tabs(["✅ Verificados (Conciliados)", "❌ Solo en App/Tiendas", "⚠️ Solo en Banco"])
            
            cols_to_drop = ['monto_num_str', 'Color_Asignado']
            
            with tab1: 
                df_show = df_verificados.drop(columns=[c for c in cols_to_drop if c in df_verificados.columns], errors='ignore')
                st.dataframe(df_show, use_container_width=True)
            with tab2: 
                df_show2 = df_solo_app.drop(columns=[c for c in cols_to_drop if c in df_solo_app.columns], errors='ignore')
                st.dataframe(df_show2, use_container_width=True)
            with tab3: 
                st.dataframe(df_solo_banco, use_container_width=True)

            # --- Descarga de Archivos ---
            st.divider()
            st.subheader("📥 Descargar Resultados")
            col_btn1, col_btn2 = st.columns(2)
            
            # Botón 1: CSV Unificado
            frames_to_concat = []
            if not df_verificados.empty: frames_to_concat.append(df_verificados)
            if not df_solo_app.empty: frames_to_concat.append(df_solo_app)
            
            if not df_solo_banco.empty:
                banco_to_export = pd.DataFrame({
                    'Tienda/App': 'No Identificado',
                    'Referencia_str': df_solo_banco['referencia_str'],
                    'Ref Banco': df_solo_banco['referencia_str'],
                    'monto_num': 0, 
                    'Monto Banco': df_solo_banco['monto_num'],
                    'Estado': df_solo_banco['Estado'],
                    'Fecha/Hora': df_solo_banco[col_fecha_banco] if col_fecha_banco else ''
                })
                frames_to_concat.append(banco_to_export)

            with col_btn1:
                if frames_to_concat:
                    df_final = pd.concat(frames_to_concat, ignore_index=True)
                    df_final = df_final.drop(columns=[c for c in cols_to_drop if c in df_final.columns], errors='ignore')
                    csv = df_final.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📄 Descargar Reporte Unificado (CSV)",
                        data=csv,
                        file_name="Auditoria_Pagos_Multitienda.csv",
                        mime="text/csv",
                        type="primary"
                    )
            
            # Botón 2: Excel Pintado con Múltiples Colores
            with col_btn2:
                def pintar_filas(row):
                    # Obtenemos el color asignado a este índice, si no hay, queda vacío
                    color_hex = banco_matched_colors.get(row.name, '')
                    style = f'background-color: {color_hex}' if color_hex else ''
                    return [style] * len(row)
                
                df_banco_export = df_banco_original.copy()
                df_banco_export.columns = df_banco_original.attrs.get('columnas_originales', df_banco_original.columns)
                styled_banco = df_banco_export.style.apply(pintar_filas, axis=1)
                
                output_excel = io.BytesIO()
                try:
                    with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                        styled_banco.to_excel(writer, index=False, sheet_name='Banco_Conciliado')
                    
                    st.download_button(
                        label="🎨 Descargar Banco Pintado (Excel)",
                        data=output_excel.getvalue(),
                        file_name="Banco_Conciliado_Colores.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                    st.caption("Leyenda: 🟡 Crediabby | 🟢 Dominga | 🟠 Varyna | 🔵 Samuel")
                except Exception as e:
                    st.error(f"Error al exportar Excel: {e}")
                    
        except Exception as e:
            import traceback
            st.error(f"Ocurrió un error inesperado durante el procesamiento: {e}")
            st.write(traceback.format_exc())
elif banco_file:
    st.info("⬆️ Sube al menos un reporte de App/Tienda para comenzar el cruce.")