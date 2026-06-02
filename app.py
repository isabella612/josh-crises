import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import io
import math

st.set_page_config(
    page_title="Diario de Crises — Josh",
    page_icon="🐾",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
/* Mobile-first: botoes largura total */
.stButton > button {
    width: 100%;
    padding: 0.6rem 1rem;
    font-size: 1rem;
}
/* Metricas mais compactas */
[data-testid="stMetric"] {
    background: #1e1e2e;
    border-radius: 12px;
    padding: 0.8rem;
    margin-bottom: 0.5rem;
}
[data-testid="stMetricLabel"] {
    font-size: 0.75rem !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.1rem !important;
}
/* Expanders mais legiveis */
[data-testid="stExpander"] {
    border-radius: 10px;
    margin-bottom: 0.4rem;
}
/* Inputs largura total */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    font-size: 1rem;
}
/* Divider mais sutil */
hr {
    margin: 0.8rem 0;
}
/* Caption menor */
.stCaption {
    font-size: 0.7rem !important;
}
</style>
""", unsafe_allow_html=True)

# ── Cliente REST Supabase ─────────────────────────────────────────────────────

class Supabase:
    def __init__(self, url: str, key: str):
        self.base = url.rstrip("/") + "/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def select(self, table: str, order: str = None) -> list:
        params = {"select": "*"}
        if order:
            params["order"] = order
        r = requests.get(f"{self.base}/{table}", headers=self.headers, params=params)
        r.raise_for_status()
        return r.json()

    def insert(self, table: str, data: dict) -> dict:
        r = requests.post(f"{self.base}/{table}", headers=self.headers, json=data)
        r.raise_for_status()
        result = r.json()
        return result[0] if isinstance(result, list) else result

    def delete(self, table: str, id_val: int):
        r = requests.delete(f"{self.base}/{table}", headers=self.headers, params={"id": f"eq.{id_val}"})
        r.raise_for_status()

    def update_by(self, table: str, data: dict, **filters):
        params = {k: f"eq.{v}" for k, v in filters.items()}
        r = requests.patch(f"{self.base}/{table}", headers=self.headers, params=params, json=data)
        r.raise_for_status()


@st.cache_resource
def get_db():
    return Supabase(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["key"],
    )


# ── Helpers de dados ──────────────────────────────────────────────────────────

def carregar_crises() -> pd.DataFrame:
    data = get_db().select("crises", order="data_hora")
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["data_hora"] = pd.to_datetime(df["data_hora"]).dt.tz_localize(None)
    return df


def salvar_crise(dados: dict):
    dados.pop("id", None)
    get_db().insert("crises", dados)


def deletar_crise(crise_id: int):
    get_db().delete("crises", crise_id)


def carregar_horarios() -> pd.DataFrame:
    data = get_db().select("horarios", order="id")
    return pd.DataFrame(data) if data else pd.DataFrame()


def atualizar_dose(medicamento: str, nova_dose: str):
    get_db().update_by("horarios", {"dose": nova_dose}, medicamento=medicamento)


def carregar_historico_doses() -> pd.DataFrame:
    data = get_db().select("historico_doses", order="data")
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["data"] = pd.to_datetime(df["data"])
    return df


def salvar_alteracao_dose(dados: dict):
    dados.pop("id", None)
    get_db().insert("historico_doses", dados)


# ── Helpers de formatação ─────────────────────────────────────────────────────

def formatar_periodo(dias: int) -> str:
    if dias == 0:
        return "hoje"
    anos = dias // 365
    resto = dias % 365
    meses = resto // 30
    dias_r = resto % 30
    partes = []
    if anos == 1:
        partes.append("1 ano")
    elif anos > 1:
        partes.append(f"{anos} anos")
    if meses == 1:
        partes.append("1 mes")
    elif meses > 1:
        partes.append(f"{meses} meses")
    if dias_r > 0 and anos == 0:
        partes.append(f"{dias_r} dias")
    return " e ".join(partes) if partes else f"{dias} dias"


def formatar_duracao(minutos, segundos):
    try:
        total = int(minutos) * 60 + int(segundos)
    except Exception:
        return "—"
    if total == 0:
        return "nao informada"
    if total < 60:
        return f"{int(segundos)}s"
    return f"{int(minutos)}min {int(segundos)}s"


def formatar_bool(valor):
    if valor is None:
        return "—"
    if isinstance(valor, bool):
        return "Sim" if valor else "Nao"
    if isinstance(valor, float) and math.isnan(valor):
        return "—"
    s = str(valor).lower().strip()
    if s in ["", "nan", "none"]:
        return "—"
    return "Sim" if s in ["true", "1", "sim", "yes"] else "Nao"


def classificar_intervalo(dias: int) -> str:
    if dias <= 7:
        return "🔴 Cluster"
    if dias <= 21:
        return "🟠 Curto"
    if dias <= 60:
        return "🟡 Medio"
    return "🟢 Longo"


def val(row, col):
    v = row.get(col, "") if isinstance(row, dict) else getattr(row, col, "")
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return str(v)


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("🐾 Josh — Diario de Crises")
pagina = st.sidebar.radio(
    "Navegacao",
    ["Registrar Crise", "Dashboard", "Medicamentos", "Relatorio para o Vet"],
)

df_crises = carregar_crises()

# ═════════════════════════════════════════════════════════════════════════════
# PÁGINA: Registrar Crise
# ═════════════════════════════════════════════════════════════════════════════
if pagina == "Registrar Crise":
    st.title("Registrar Nova Crise")

    with st.form("form_crise", clear_on_submit=True):
        st.subheader("Data e Hora")
        col1, col2 = st.columns(2)
        with col1:
            data = st.date_input("Data da crise", value=datetime.now().date())
        with col2:
            hora = st.time_input("Hora da crise", value=datetime.now().time())

        st.divider()
        st.subheader("Duracao")
        col1, col2 = st.columns(2)
        with col1:
            duracao_min = st.number_input("Minutos", min_value=0, max_value=60, value=0)
        with col2:
            duracao_seg = st.number_input("Segundos", min_value=0, max_value=59, value=0)

        st.divider()
        st.subheader("Antes da Crise — Sinais")
        antes_sinais = st.text_area(
            "O que voce observou antes da crise comecar?",
            placeholder="Ex: estava agitado, escondido, chorando, andando em circulos...",
            height=100,
        )

        st.divider()
        st.subheader("Durante a Crise — Sintomas")
        col1, col2 = st.columns(2)
        with col1:
            durante_corpo_todo = st.checkbox("Tremeu o corpo todo")
            durante_rigidez = st.checkbox("Ficou rigido (tonico)")
            durante_salivacao = st.checkbox("Salivou muito / babou")
        with col2:
            durante_urinacao = st.checkbox("Urinou involuntariamente")
            durante_defecacao = st.checkbox("Defecou involuntariamente")
        durante_parte_corpo = st.text_input(
            "Se tremeu apenas uma parte, qual?",
            placeholder="Ex: pata traseira direita, cabeca...",
        )

        st.divider()
        st.subheader("Depois da Crise — Recuperacao")
        apos_tempo_recuperacao = st.text_input(
            "Quanto tempo levou para voltar ao normal?",
            placeholder="Ex: 10 minutos, 1 hora...",
        )
        apos_desorientado = st.checkbox("Ficou desorientado")
        apos_fome = st.checkbox("Ficou com muita fome")
        apos_cambaleando = st.checkbox("Ficou cambaleando")

        st.divider()
        st.subheader("Medicacao")
        medicacao_tomou = st.selectbox(
            "Tomou a medicacao anticonvulsivante corretamente no dia?",
            ["Sim", "Nao", "Nao sei"],
        )
        medicacao_obs = st.text_input(
            "Observacoes sobre a medicacao",
            placeholder="Ex: dose atrasada 2h, nova medicacao ha 3 dias...",
        )

        st.divider()
        st.subheader("Observacoes do Dia")
        observacoes_dia = st.text_area(
            "O que aconteceu de diferente no dia?",
            placeholder="Ex: fogos, mudanca de racao, banho, visita, muito calor, viagem...",
            height=100,
        )

        if st.form_submit_button("Salvar Crise", type="primary", use_container_width=True):
            salvar_crise({
                "data_hora": datetime.combine(data, hora).isoformat(),
                "duracao_min": int(duracao_min),
                "duracao_seg": int(duracao_seg),
                "antes_sinais": antes_sinais,
                "durante_corpo_todo": durante_corpo_todo,
                "durante_parte_corpo": durante_parte_corpo,
                "durante_rigidez": durante_rigidez,
                "durante_salivacao": durante_salivacao,
                "durante_urinacao": durante_urinacao,
                "durante_defecacao": durante_defecacao,
                "apos_tempo_recuperacao": apos_tempo_recuperacao,
                "apos_desorientado": apos_desorientado,
                "apos_fome": apos_fome,
                "apos_cambaleando": apos_cambaleando,
                "medicacao_tomou": medicacao_tomou,
                "medicacao_obs": medicacao_obs,
                "observacoes_dia": observacoes_dia,
            })
            st.success("Crise registrada com sucesso!")
            st.balloons()
            st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# PÁGINA: Dashboard
# ═════════════════════════════════════════════════════════════════════════════
elif pagina == "Dashboard":
    st.title("Dashboard de Crises — Josh")

    col1, col2 = st.columns(2)
    with col1:
        st.image("images/josh_filhote.jpg", caption="Josh filhote", use_container_width=True)
    with col2:
        st.image("images/josh_adulto.jpg", caption="Josh hoje", use_container_width=True)

    st.markdown("""
    <div style='text-align: center; padding: 1rem 0.5rem; font-style: italic; font-size: 1rem; line-height: 1.6; color: #ccc;'>
    "Josh nos ensina todos os dias que família não é sobre ser perfeito.<br>
    É sobre estar junto, cuidar, e escolher ficar — todos os dias.<br>
    O amor mais puro e verdadeiro."
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    if df_crises.empty:
        st.info("Nenhuma crise registrada ainda.")
    else:
        df_sorted = df_crises.sort_values("data_hora").reset_index(drop=True)

        intervalos = []
        for i in range(1, len(df_sorted)):
            delta = df_sorted.loc[i, "data_hora"] - df_sorted.loc[i - 1, "data_hora"]
            intervalos.append(delta.total_seconds() / 86400)

        ultima_crise = df_sorted["data_hora"].max()
        dias_desde_ultima = (datetime.now() - ultima_crise).days

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total de Crises", len(df_crises))
            st.metric("Sem crise ha", formatar_periodo(dias_desde_ultima))
        with col2:
            st.metric("Ultima Crise", ultima_crise.strftime("%d/%m/%Y"))
            if intervalos:
                st.metric("Intervalo medio", formatar_periodo(int(sum(intervalos) / len(intervalos))))
            else:
                st.metric("Intervalo medio", "—")

        if intervalos:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Menor intervalo", formatar_periodo(int(min(intervalos))))
            with col2:
                st.metric("Maior intervalo", formatar_periodo(int(max(intervalos))))

        st.divider()
        st.subheader("Crises por Mes")
        df_sorted["mes"] = df_sorted["data_hora"].dt.to_period("M").astype(str)
        crises_por_mes = df_sorted.groupby("mes").size().reset_index(name="quantidade")
        st.bar_chart(crises_por_mes.set_index("mes")["quantidade"])

        st.divider()
        st.subheader("Historico de Crises")
        st.caption("🔴 Cluster (ate 7 dias)  |  🟠 Curto (ate 21 dias)  |  🟡 Medio (ate 60 dias)  |  🟢 Longo (mais de 60 dias)")
        df_rev = df_sorted[::-1].reset_index(drop=True)
        for i, row in df_rev.iterrows():
            idx_original = len(df_sorted) - 1 - i
            if idx_original > 0:
                delta = df_sorted.loc[idx_original, "data_hora"] - df_sorted.loc[idx_original - 1, "data_hora"]
                dias_int = int(delta.total_seconds() / 86400)
                badge = classificar_intervalo(dias_int)
                intervalo_label = f"  {badge} {formatar_periodo(dias_int)} desde a anterior"
            else:
                intervalo_label = "  — primeira crise registrada"

            duracao = formatar_duracao(row.get("duracao_min", 0), row.get("duracao_seg", 0))
            with st.expander(
                f"Crise #{int(row['id'])} — {pd.to_datetime(row['data_hora']).strftime('%d/%m/%Y %H:%M')}{intervalo_label}"
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Duracao:** {duracao}")
                    st.markdown(f"**Antes:** {val(row, 'antes_sinais') or '—'}")
                    st.markdown(f"**Corpo todo:** {formatar_bool(row.get('durante_corpo_todo'))}")
                    st.markdown(f"**Parte afetada:** {val(row, 'durante_parte_corpo') or '—'}")
                    st.markdown(f"**Rigidez:** {formatar_bool(row.get('durante_rigidez'))}")
                with col2:
                    st.markdown(f"**Salivacao:** {formatar_bool(row.get('durante_salivacao'))}")
                    st.markdown(f"**Urinacao:** {formatar_bool(row.get('durante_urinacao'))}")
                    st.markdown(f"**Recuperacao:** {val(row, 'apos_tempo_recuperacao') or '—'}")
                    st.markdown(f"**Desorientado:** {formatar_bool(row.get('apos_desorientado'))}")
                    st.markdown(f"**Medicacao:** {val(row, 'medicacao_tomou') or '—'}")
                obs = val(row, "observacoes_dia")
                if obs:
                    st.info(f"Obs do dia: {obs}")
                if st.button("Deletar esta crise", key=f"del_{int(row['id'])}"):
                    deletar_crise(int(row["id"]))
                    st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# PÁGINA: Medicamentos
# ═════════════════════════════════════════════════════════════════════════════
elif pagina == "Medicamentos":
    st.title("Medicamentos e Horarios")

    df_horarios = carregar_horarios()
    df_doses = carregar_historico_doses()

    st.subheader("Sequencia sem crises")

    if df_crises.empty:
        st.info("Nenhuma crise registrada ainda.")
    else:
        ultima_crise = df_crises.sort_values("data_hora")["data_hora"].max()
        dias_sem_crise = (datetime.now() - ultima_crise).days

        st.markdown(f"### Josh esta ha **{formatar_periodo(dias_sem_crise)}** sem crises")
        st.caption(f"Ultima crise registrada: {ultima_crise.strftime('%d/%m/%Y')}")

        st.markdown("")
        st.markdown("**Marcos alcancados:**")

        MARCOS = [
            (7,   "1 semana"),
            (30,  "1 mes"),
            (90,  "3 meses"),
            (180, "6 meses"),
            (365, "1 ano"),
        ]

        for dias_marco, label in MARCOS:
            if dias_sem_crise >= dias_marco:
                data_marco = ultima_crise + timedelta(days=dias_marco)
                st.success(f"**{label}** — alcancado em {data_marco.strftime('%d/%m/%Y')}")
            else:
                faltam = dias_marco - dias_sem_crise
                st.markdown(f"⬜ **{label}** — em andamento")

    st.divider()
    st.subheader("Horarios Atuais")

    if not df_horarios.empty:
        for periodo in ["Manhã", "Tarde", "Noite"]:
            df_per = df_horarios[df_horarios["periodo"] == periodo]
            if df_per.empty:
                continue
            st.markdown(f"**{periodo}**")
            for _, row in df_per.iterrows():
                dose = val(row, "dose")
                unidade = val(row, "unidade")
                dose_str = f" — **{dose} {unidade}**" if dose else ""
                st.markdown(f"&nbsp;&nbsp;&nbsp;`{row['horario']}` {row['medicamento']}{dose_str}")
            st.write("")

    with st.expander("Editar doses atuais"):
        if not df_horarios.empty:
            meds = df_horarios[df_horarios["medicamento"].isin(["Keppra", "Gardenal"])]["medicamento"].unique().tolist()
            with st.form("form_doses"):
                novos = {}
                for med in meds:
                    rows_med = df_horarios[df_horarios["medicamento"] == med]
                    dose_atual = val(rows_med.iloc[0], "dose") if not rows_med.empty else ""
                    novos[med] = st.text_input(f"Dose do {med} (mg)", value=dose_atual, key=f"d_{med}")
                if st.form_submit_button("Salvar doses", type="primary"):
                    for med, dose in novos.items():
                        atualizar_dose(med, dose)
                    st.success("Doses atualizadas!")
                    st.rerun()

    st.divider()
    st.subheader("Registrar Alteracao de Dose")
    st.caption("Use sempre que o neurologista mudar a dose do Gardenal ou Keppra.")

    with st.form("form_alt_dose", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            data_alt = st.date_input("Data", value=datetime.now().date())
            med_alt = st.selectbox("Medicamento", ["Gardenal", "Keppra"])
        with col2:
            dose_ant = st.text_input("Dose anterior (mg)", placeholder="Ex: 100")
            dose_nov = st.text_input("Dose nova (mg)", placeholder="Ex: 75")
        motivo = st.text_area("Motivo / orientacao do neurologista", height=80)

        if st.form_submit_button("Registrar Alteracao", type="primary", use_container_width=True):
            if not dose_nov.strip():
                st.error("Informe a nova dose.")
            else:
                salvar_alteracao_dose({
                    "data": data_alt.isoformat(),
                    "medicamento": med_alt,
                    "dose_anterior": dose_ant,
                    "dose_nova": dose_nov,
                    "unidade": "mg",
                    "motivo": motivo,
                })
                atualizar_dose(med_alt, dose_nov)
                st.success(f"Alteracao de {med_alt} registrada!")
                st.rerun()

    st.divider()
    st.subheader("Historico de Alteracoes de Dose")

    if df_doses.empty:
        st.info("Nenhuma alteracao registrada ainda.")
    else:
        for _, row in df_doses.sort_values("data", ascending=False).iterrows():
            data_fmt = pd.to_datetime(row["data"]).strftime("%d/%m/%Y")
            ant = f"{val(row, 'dose_anterior')} mg" if val(row, "dose_anterior") else "—"
            nova = f"{val(row, 'dose_nova')} mg"
            with st.expander(f"{row['medicamento']} — {data_fmt} — {ant} -> {nova}"):
                st.markdown(f"**Data:** {data_fmt}")
                st.markdown(f"**Dose anterior:** {ant}  |  **Nova dose:** {nova}")
                st.markdown(f"**Motivo:** {val(row, 'motivo') or '—'}")

# ═════════════════════════════════════════════════════════════════════════════
# PÁGINA: Relatório
# ═════════════════════════════════════════════════════════════════════════════
elif pagina == "Relatorio para o Vet":
    st.title("Relatorio para o Neurologista")

    if df_crises.empty:
        st.info("Nenhuma crise registrada ainda.")
    else:
        df_sorted = df_crises.sort_values("data_hora").reset_index(drop=True)
        ultima = df_sorted["data_hora"].max()
        primeira = df_sorted["data_hora"].min()
        penultima = df_sorted["data_hora"].iloc[-2] if len(df_sorted) >= 2 else None

        col1, col2 = st.columns(2)
        with col1:
            data_inicio = st.date_input("De", value=primeira.date())
        with col2:
            data_fim = st.date_input("Ate", value=ultima.date())

        df_f = df_sorted[
            (df_sorted["data_hora"].dt.date >= data_inicio) &
            (df_sorted["data_hora"].dt.date <= data_fim)
        ].reset_index(drop=True)

        df_horarios = carregar_horarios()
        df_doses = carregar_historico_doses()

        intervalos = []
        for i in range(1, len(df_f)):
            delta = df_f.loc[i, "data_hora"] - df_f.loc[i - 1, "data_hora"]
            intervalos.append(delta.total_seconds() / 86400)

        dias_sem_crise = (datetime.now() - ultima).days

        st.markdown("---")
        st.subheader("Resumo Geral")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total de crises", len(df_f))
            if intervalos:
                st.metric("Menor intervalo", formatar_periodo(int(min(intervalos))))
        with col2:
            st.metric("Sem crise ha", formatar_periodo(dias_sem_crise))
            if intervalos:
                st.metric("Maior intervalo", formatar_periodo(int(max(intervalos))))
        if intervalos:
            st.metric("Intervalo medio", formatar_periodo(int(sum(intervalos) / len(intervalos))))

        if penultima is not None:
            dias_final = int((ultima - penultima).total_seconds() / 86400)
            st.info(
                f"Penultima crise: {penultima.strftime('%d/%m/%Y')}  |  "
                f"Ultima crise: {ultima.strftime('%d/%m/%Y')}  |  "
                f"Intervalo: **{formatar_periodo(dias_final)}** ({dias_final} dias)"
            )

        st.markdown("---")
        st.subheader("Linha do Tempo com Intervalos")

        tabela_rows = []
        for i, row in df_f.iterrows():
            if i == 0:
                intervalo_str = "— primeira"
                badge = ""
            else:
                delta = df_f.loc[i, "data_hora"] - df_f.loc[i - 1, "data_hora"]
                dias_int = int(delta.total_seconds() / 86400)
                intervalo_str = formatar_periodo(dias_int)
                badge = classificar_intervalo(dias_int)
            obs = val(row, "observacoes_dia")
            tabela_rows.append({
                "Data": pd.to_datetime(row["data_hora"]).strftime("%d/%m/%Y"),
                "Hora": pd.to_datetime(row["data_hora"]).strftime("%H:%M"),
                "Desde a anterior": intervalo_str,
                "Tipo": badge,
                "Obs": obs[:60] + "..." if len(obs) > 60 else obs,
            })

        st.dataframe(pd.DataFrame(tabela_rows), use_container_width=True, hide_index=True)
        st.caption("🔴 Cluster (ate 7 dias)  |  🟠 Curto (ate 21 dias)  |  🟡 Medio (ate 60 dias)  |  🟢 Longo (mais de 60 dias)")

        st.markdown("---")
        st.subheader("Medicacao Atual")
        if not df_horarios.empty:
            for periodo in ["Manhã", "Tarde", "Noite"]:
                df_per = df_horarios[df_horarios["periodo"] == periodo]
                if df_per.empty:
                    continue
                st.markdown(f"**{periodo}**")
                for _, row in df_per.iterrows():
                    dose = val(row, "dose")
                    dose_str = f" — {dose} {val(row, 'unidade')}" if dose else ""
                    st.markdown(f"&nbsp;&nbsp;`{row['horario']}` {row['medicamento']}{dose_str}")

        if not df_doses.empty:
            df_doses_periodo = df_doses[
                (pd.to_datetime(df_doses["data"]).dt.date >= data_inicio) &
                (pd.to_datetime(df_doses["data"]).dt.date <= data_fim)
            ]
            if not df_doses_periodo.empty:
                st.markdown("**Alteracoes de dose no periodo:**")
                for _, row in df_doses_periodo.sort_values("data").iterrows():
                    data_fmt = pd.to_datetime(row["data"]).strftime("%d/%m/%Y")
                    ant = f"{val(row, 'dose_anterior')} mg" if val(row, "dose_anterior") else "—"
                    st.markdown(f"- {data_fmt}: {row['medicamento']} {ant} -> {val(row, 'dose_nova')} mg — {val(row, 'motivo')}")

        st.markdown("---")
        st.subheader("Detalhamento por Crise")
        for i, row in df_f.iterrows():
            data_hora_fmt = pd.to_datetime(row["data_hora"]).strftime("%d/%m/%Y as %H:%M")
            duracao = formatar_duracao(row.get("duracao_min", 0), row.get("duracao_seg", 0))
            if i == 0:
                int_label = "primeira crise do periodo"
            else:
                delta = df_f.loc[i, "data_hora"] - df_f.loc[i - 1, "data_hora"]
                dias_int = int(delta.total_seconds() / 86400)
                int_label = f"{classificar_intervalo(dias_int)} {formatar_periodo(dias_int)} desde a anterior"

            with st.expander(f"Crise #{int(row['id'])} — {data_hora_fmt} — {int_label}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Duracao:** {duracao}")
                    st.markdown(f"**Antes:** {val(row, 'antes_sinais') or '—'}")
                    st.markdown(f"**Corpo todo:** {formatar_bool(row.get('durante_corpo_todo'))}")
                    st.markdown(f"**Parte afetada:** {val(row, 'durante_parte_corpo') or '—'}")
                    st.markdown(f"**Rigidez:** {formatar_bool(row.get('durante_rigidez'))}")
                with col2:
                    st.markdown(f"**Salivacao:** {formatar_bool(row.get('durante_salivacao'))}")
                    st.markdown(f"**Urinacao:** {formatar_bool(row.get('durante_urinacao'))}")
                    st.markdown(f"**Recuperacao:** {val(row, 'apos_tempo_recuperacao') or '—'}")
                    st.markdown(f"**Medicacao:** {val(row, 'medicacao_tomou') or '—'}")
                obs = val(row, "observacoes_dia")
                if obs:
                    st.info(f"Obs: {obs}")

        st.markdown("---")
        linhas = [
            "RELATORIO DE CRISES EPILEPTICAS — JOSH",
            "=" * 55,
            f"Periodo: {data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}",
            f"Total de crises: {len(df_f)}",
            f"Sem crise ha: {formatar_periodo(dias_sem_crise)}",
        ]
        if intervalos:
            linhas += [
                f"Intervalo medio: {formatar_periodo(int(sum(intervalos)/len(intervalos)))}",
                f"Menor intervalo: {formatar_periodo(int(min(intervalos)))}",
                f"Maior intervalo: {formatar_periodo(int(max(intervalos)))}",
            ]
        if penultima is not None:
            linhas.append(f"Penultima -> Ultima: {formatar_periodo(dias_final)} ({dias_final} dias)")
        linhas.append("")
        linhas.append("LINHA DO TEMPO")
        linhas.append("-" * 55)
        for r in tabela_rows:
            linhas.append(f"  {r['Data']} {r['Hora']}  |  {r['Desde a anterior']}  {r['Tipo']}")
            if r["Obs"]:
                linhas.append(f"    Obs: {r['Obs']}")

        buffer = io.BytesIO("\n".join(linhas).encode("utf-8"))
        st.download_button(
            label="Baixar relatorio (.txt)",
            data=buffer,
            file_name=f"relatorio_josh_{data_inicio.strftime('%Y%m%d')}_{data_fim.strftime('%Y%m%d')}.txt",
            mime="text/plain",
            type="primary",
            use_container_width=True,
        )
