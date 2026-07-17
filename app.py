import streamlit as st
import pandas as pd
import io

# Configuración básica de la página
st.set_page_config(page_title="Conciliación Crediabby", page_icon="💸", layout="wide")

st.title("💸 Conciliador de Pagos: Crediabby vs Banco de Venezuela")

st.markdown('''
Sube tus reportes diarios para cruzar la información. El sistema buscará de manera inteligente las coincidencias de los números de referencia (incluso si están incompletos) y validará los montos en bolívares.
''')

# Crear dos columnas para subir los archivos
col1, col2 = st.columns(2)
with col1:
    banco_file = st.file_uploader("📂 Sube el archivo del Banco de Venezuela", type=["xlsx", "xls", "csv"])
with col2:
    app_file = st.file_uploader("📂 Sube el reporte de la App Móvil", type=["xlsx", "xls", "csv"])

# Función para limpiar y convertir los montos del banco a números matemáticos
def parse_monto_banco(val):
    if pd.isna(val): return 0.0
    val_str = str(val).strip().replace('.', '').replace(',', '.')
    try: return float(val_str)
    except: return 0.0

# Función robusta para cargar datos y limpiar nombres de columnas
def load_data(file):
    try:
        file.seek(0) # REBOBINAR EL ARCHIVO: Evita que Streamlit lea archivos vacíos al recargar
        if file.name.lower().endswith('.csv'):
            df = pd.read_csv(file)
            # Si detecta 1 sola columna o menos, probablemente el separador de Excel fue punto y coma (;)
            if len(df.columns) <= 1:
                file.seek(0)
                df = pd.read_csv(file, sep=';')
        else:
            # LEER EXCEL MULTI-PESTAÑA: Carga todas las hojas del Excel
            xls = pd.read_excel(file, sheet_name=None)
            df = pd.DataFrame() # DataFrame vacío por defecto
            
            # Buscar automáticamente la primera pestaña que sí tenga datos
            for sheet_name, sheet_df in xls.items():
                if not sheet_df.empty and len(sheet_df.columns) > 0:
                    df = sheet_df
                    break
            
        if len(df.columns) == 0:
            st.error(f"⚠️ El archivo {file.name} se leyó vacío. Verifica que tenga información.")
            return None
        
        # Guardamos los nombres originales para el reporte marcado
        df.attrs['columnas_originales'] = df.columns.tolist()
        
        # Estandarizar nombres de columnas: convertimos a texto (str) primero para evitar errores con números
        df.columns = df.columns.astype(str).str.strip().str.lower()
        return df
    except Exception as e:
        st.error(f"Error al leer el archivo {file.name}: {e}")
        return None

# Función auxiliar para encontrar el nombre real de una columna en base a una palabra clave
def find_column(df, keyword):
    keyword = keyword.lower().strip()
    for col in df.columns:
        col_str = str(col).lower().strip()
        if keyword in col_str:
            return col
    return None

# Lógica principal si ambos archivos han sido subidos
if banco_file and app_file:
    df_banco_original = load_data(banco_file)
    df_app = load_data(app_file)
    
    if df_banco_original is not None and df_app is not None:
        try:
            # Encontrar las columnas dinámicamente para evitar errores de tipeo en los archivos
            col_ref_banco = find_column(df_banco_original, 'referencia') or find_column(df_banco_original, 'ref')
            col_monto_banco = find_column(df_banco_original, 'monto')
            col_tipo_banco = find_column(df_banco_original, 'tipomovimiento') or find_column(df_banco_original, 'concepto')
            col_fecha_banco = find_column(df_banco_original, 'fecha')
            
            col_ref_app = find_column(df_app, 'referencia') or find_column(df_app, 'ref')
            col_monto_app = find_column(df_app, 'bs') or find_column(df_app, 'monto')

            if not col_ref_banco or not col_monto_banco:
                st.error(f"❌ No se encontraron las columnas de Referencia o Monto en el archivo del **Banco**.")
                st.info(f"Columnas detectadas en el Banco: {list(df_banco_original.columns)}")
                st.stop()
                
            if not col_ref_app or not col_monto_app:
                st.error(f"❌ No se encontraron las columnas de Referencia o Monto en el archivo de la **App**.")
                st.info(f"Columnas detectadas en la App: {list(df_app.columns)}")
                st.stop()

            # --- Limpieza del Banco ---
            # Trabajamos sobre una copia para no alterar el original que vamos a descargar coloreado
            if col_tipo_banco:
                df_banco_ingresos = df_banco_original[df_banco_original[col_tipo_banco].astype(str).str.contains('Crédito', case=False, na=False)].copy()
            else:
                df_banco_ingresos = df_banco_original[~df_banco_original[col_monto_banco].astype(str).str.contains('-')].copy()
                
            df_banco_ingresos['monto_num'] = df_banco_ingresos[col_monto_banco].apply(parse_monto_banco)
            df_banco_ingresos['referencia_str'] = df_banco_ingresos[col_ref_banco].astype(str).str.strip().str.replace('.0', '', regex=False)
            
            # --- Limpieza de la App ---
            df_app['Referencia_str'] = df_app[col_ref_app].astype(str).str.strip().str.replace('.0', '', regex=False)
            df_app['monto_num_str'] = df_app[col_monto_app].astype(str).str.replace(',', '.')
            df_app['monto_num'] = pd.to_numeric(df_app['monto_num_str'], errors='coerce').fillna(0)
            
            # --- Motor de Conciliación ---
            verificados = []
            solo_app = []
            banco_matched_indices = set() 
            
            for idx_app, row_app in df_app.iterrows():
                ref_app = str(row_app['Referencia_str']).strip().replace('.0', '')
                if ref_app.lower() in ['nan', 'none', 'nat', ''] or pd.isna(row_app['Referencia_str']):
                    continue
                
                monto_app = row_app['monto_num']
                
                posibles_matches = df_banco_ingresos[
                    df_banco_ingresos['referencia_str'].str.endswith(ref_app) & 
                    (~df_banco_ingresos.index.isin(banco_matched_indices))
                ]
                
                match_encontrado = False
                if not posibles_matches.empty:
                    # Buscar entre las posibles referencias la que también coincida en monto
                    for idx_banco, match_banco in posibles_matches.iterrows():
                        monto_banco = match_banco['monto_num']
                        if abs(monto_app - monto_banco) <= 1.0:
                            banco_matched_indices.add(idx_banco) # Marcamos como usada
                            verificados.append({**row_app.to_dict(), 'Ref Banco': match_banco['referencia_str'], 'Monto Banco': monto_banco, 'Estado': 'Verificado'})
                            match_encontrado = True
                            break
                
                if not match_encontrado:
                    row_dict = row_app.to_dict()
                    row_dict['Estado'] = 'Solo en App'
                    solo_app.append(row_dict)
                    
            df_solo_banco = df_banco_ingresos[~df_banco_ingresos.index.isin(banco_matched_indices)].copy()
            df_solo_banco['Estado'] = 'Solo en Banco'
            
            df_verificados = pd.DataFrame(verificados)
            df_solo_app = pd.DataFrame(solo_app)

            # --- Interfaz Visual de Resultados ---
            st.divider()
            st.subheader("📊 Resumen de la Conciliación")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("✅ Verificados (Conciliados)", len(df_verificados))
            c2.metric("❌ Solo App (No en Banco)", len(df_solo_app))
            c3.metric("⚠️ Solo Banco (No en App)", len(df_solo_banco))
            
            tab1, tab2, tab3 = st.tabs(["✅ Verificados", "❌ Faltan en Banco", "⚠️ Faltan en App"])
            
            with tab1: st.dataframe(df_verificados, use_container_width=True)
            with tab2: st.dataframe(df_solo_app, use_container_width=True)
            with tab3: st.dataframe(df_solo_banco, use_container_width=True)
                
            # --- Botones de Descarga ---
            st.divider()
            st.subheader("📥 Descargar Resultados")
            col_btn1, col_btn2 = st.columns(2)
            
            # 1. Botón CSV (Reporte general)
            frames_to_concat = []
            if not df_verificados.empty: frames_to_concat.append(df_verificados)
            if not df_solo_app.empty: frames_to_concat.append(df_solo_app)
            
            if not df_solo_banco.empty:
                banco_to_export = pd.DataFrame({
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
                    csv = df_final.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📄 Descargar Auditoría (CSV)",
                        data=csv,
                        file_name="Auditoria_Pago_Movil.csv",
                        mime="text/csv",
                        type="primary"
                    )
                else:
                    st.info("No hay datos para exportar en CSV.")
            
            # 2. Botón Excel Banco Resaltado
            with col_btn2:
                # Función para pintar de amarillo las filas conciliadas
                def pintar_filas(row):
                    # Si el índice de la fila está en los que verificamos, se pinta amarillo claro
                    color = 'background-color: #FFFF99' if row.name in banco_matched_indices else ''
                    return [color] * len(row)
                
                # Restaurar los nombres originales de las columnas para el reporte
                df_banco_export = df_banco_original.copy()
                df_banco_export.columns = df_banco_original.attrs.get('columnas_originales', df_banco_original.columns)
                
                # Aplicamos el estilo
                styled_banco = df_banco_export.style.apply(pintar_filas, axis=1)
                
                output_excel = io.BytesIO()
                try:
                    # Usamos xlsxwriter que es el motor oficial para escribir estilos en pandas
                    with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                        styled_banco.to_excel(writer, index=False, sheet_name='Banco_Conciliado')
                    
                    st.download_button(
                        label="🟨 Descargar Banco Marcado (Excel)",
                        data=output_excel.getvalue(),
                        file_name="Banco_Marcado_Amarillo.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="secondary"
                    )
                except Exception as e:
                    st.error(f"Falta librería para exportar Excel marcado. Detalle: {e}")
            
        except Exception as e:
            import traceback
            st.error(f"Ocurrió un error inesperado durante el procesamiento: {e}")
            st.write(traceback.format_exc())