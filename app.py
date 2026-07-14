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

# Función robusta para cargar datos
def load_data(file):
    try:
        if file.name.endswith('.csv'):
            return pd.read_csv(file)
        else:
            return pd.read_excel(file)
    except Exception as e:
        st.error(f"Error al leer el archivo {file.name}: {e}")
        return None

# Lógica principal si ambos archivos han sido subidos
if banco_file and app_file:
    df_banco = load_data(banco_file)
    df_app = load_data(app_file)
    
    if df_banco is not None and df_app is not None:
        try:
            # --- Limpieza del Banco ---
            # Filtramos para quedarnos únicamente con los ingresos (Notas de Crédito)
            if 'tipoMovimiento' in df_banco.columns:
                df_banco = df_banco[df_banco['tipoMovimiento'].str.contains('Crédito', case=False, na=False)].copy()
            else:
                # Alternativa por si cambia el formato: descartar montos negativos
                df_banco = df_banco[~df_banco['monto'].astype(str).str.contains('-')].copy()
                
            # Limpiamos montos y referencias del banco
            df_banco['monto_num'] = df_banco['monto'].apply(parse_monto_banco)
            df_banco['referencia_str'] = df_banco['referencia'].astype(str).str.strip().str.replace('.0', '', regex=False)
            
            # --- Limpieza de la App ---
            # Limpiamos montos y referencias de la app
            df_app['Referencia_str'] = df_app['Referencia'].astype(str).str.strip().str.replace('.0', '', regex=False)
            df_app['monto_num'] = pd.to_numeric(df_app['Monto (Bs.)'], errors='coerce').fillna(0)
            
            # --- Motor de Conciliación ---
            verificados = []
            solo_app = []
            diferencia_monto = []
            
            # Set para rastrear transacciones del banco ya conciliadas y no duplicar
            banco_matched_indices = set() 
            
            for idx_app, row_app in df_app.iterrows():
                ref_app = row_app['Referencia_str']
                monto_app = row_app['monto_num']
                
                # Buscar coincidencia: el final del número de ref del banco debe empatar con la ref de la app
                posibles_matches = df_banco[
                    df_banco['referencia_str'].str.endswith(ref_app) & 
                    (~df_banco.index.isin(banco_matched_indices))
                ]
                
                if not posibles_matches.empty:
                    # Tomamos la primera coincidencia que encontremos
                    match_banco = posibles_matches.iloc[0]
                    idx_banco = posibles_matches.index[0]
                    banco_matched_indices.add(idx_banco) # Marcamos como usada
                    
                    monto_banco = match_banco['monto_num']
                    
                    # Tolerancia de diferencia (1 bolívar) por temas de decimales
                    if abs(monto_app - monto_banco) <= 1.0:
                        verificados.append({**row_app.to_dict(), 'Ref Banco': match_banco['referencia_str'], 'Monto Banco': monto_banco, 'Estado': 'Verificado'})
                    else:
                        diferencia_monto.append({**row_app.to_dict(), 'Ref Banco': match_banco['referencia_str'], 'Monto Banco': monto_banco, 'Diferencia': monto_app - monto_banco, 'Estado': 'Diferencia Monto'})
                else:
                    # Si no se encontró en el banco
                    row_dict = row_app.to_dict()
                    row_dict['Estado'] = 'Solo en App'
                    solo_app.append(row_dict)
                    
            # Guardamos todo lo que sobró en el banco sin cruzar
            df_solo_banco = df_banco[~df_banco.index.isin(banco_matched_indices)].copy()
            df_solo_banco['Estado'] = 'Solo en Banco'
            
            # Convertir todo a DataFrames (Tablas de Pandas) para mostrarlos
            df_verificados = pd.DataFrame(verificados)
            df_solo_app = pd.DataFrame(solo_app)
            df_diferencia_monto = pd.DataFrame(diferencia_monto)
            
            # --- Interfaz Visual de Resultados ---
            st.divider()
            st.subheader("📊 Resumen de la Conciliación")
            
            # Tarjetas de resumen
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("✅ Verificados (Conciliados)", len(df_verificados))
            c2.metric("❌ Solo en App (No en Banco)", len(df_solo_app))
            c3.metric("⚠️ Solo en Banco (No en App)", len(df_solo_banco))
            c4.metric("⚖️ Diferencia de Monto", len(df_diferencia_monto))
            
            # Pestañas con las tablas de datos
            tab1, tab2, tab3, tab4 = st.tabs(["✅ Verificados", "❌ Faltan en Banco", "⚠️ Faltan en App", "⚖️ Diferencias"])
            
            with tab1: 
                st.dataframe(df_verificados, use_container_width=True)
            with tab2: 
                st.dataframe(df_solo_app, use_container_width=True)
            with tab3: 
                # Del banco solo mostramos lo más relevante
                st.dataframe(df_solo_banco[['fecha', 'referencia', 'concepto', 'monto', 'monto_num', 'Estado']], use_container_width=True)
            with tab4: 
                st.dataframe(df_diferencia_monto, use_container_width=True)
                
            # --- Botón de Descarga (CSV en lugar de Excel para evitar errores de librerías) ---
            st.divider()
            st.subheader("Descargar Resultados")
            
            # Combinamos todos los resultados en un solo DataFrame para el CSV
            frames_to_concat = []
            if not df_verificados.empty: frames_to_concat.append(df_verificados)
            if not df_solo_app.empty: frames_to_concat.append(df_solo_app)
            if not df_diferencia_monto.empty: frames_to_concat.append(df_diferencia_monto)
            
            # Formatear el DataFrame del banco para que tenga columnas similares si es posible
            if not df_solo_banco.empty:
                banco_to_export = pd.DataFrame({
                    'Referencia_str': df_solo_banco['referencia_str'],
                    'Ref Banco': df_solo_banco['referencia_str'],
                    'monto_num': 0, # No hay monto en app
                    'Monto Banco': df_solo_banco['monto_num'],
                    'Estado': df_solo_banco['Estado'],
                    'Fecha/Hora': df_solo_banco['fecha']
                })
                frames_to_concat.append(banco_to_export)

            if frames_to_concat:
                df_final = pd.concat(frames_to_concat, ignore_index=True)
                
                # Convertir a CSV
                csv = df_final.to_csv(index=False).encode('utf-8')
                
                st.download_button(
                    label="📥 Descargar Reporte de Auditoría (CSV)",
                    data=csv,
                    file_name="Auditoria_Pago_Movil.csv",
                    mime="text/csv",
                    type="primary"
                )
            else:
                st.info("No hay datos para exportar.")
            
        except Exception as e:
            st.error(f"Ocurrió un error inesperado durante el procesamiento: {e}")