import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from fast_pwl_fit import FastPWLFit
import io

st.set_page_config(layout="wide")

st.title("Interactive Change-Point Detection with Piecewise Linear Fitting")
st.markdown("An interactive GUI for detecting change-points in gradually sloped data.")

# --- Sidebar for Controls ---
st.sidebar.title("Controls")

uploaded_file = st.sidebar.file_uploader(
    "Upload Data File",
    type=["csv", "xlsx", "txt", "dat"],
    help="Limit 200MB per file • TXT, CSV, DAT, XLSX"
)

# Initialize session state variables
if 'data' not in st.session_state:
    st.session_state.data = None
if 'pwlf' not in st.session_state:
    st.session_state.pwlf = None

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv') or uploaded_file.name.endswith('.txt') or uploaded_file.name.endswith('.dat'):
            st.session_state.data = pd.read_csv(uploaded_file)
        else:
            st.session_state.data = pd.read_excel(uploaded_file)
        # Clear previous fit when a new file is uploaded
        st.session_state.pwlf = None
    except Exception as e:
        st.error(f"Error reading file: {e}")
        st.session_state.data = None
        st.stop()
else:
    st.info("Upload a data file to start the analysis.")
    st.stop()

if st.session_state.data is not None:
    data = st.session_state.data
    st.sidebar.subheader("Analysis Parameters")
    
    columns = data.columns.tolist()
    if not columns:
        st.error("The uploaded file has no columns.")
        st.stop()

    x_col_index = columns.index('time_pol') if 'time_pol' in columns else 0
    y_col_index = columns.index('basepairs_pol') if 'basepairs_pol' in columns else 1 if len(columns) > 1 else 0

    x_col = st.sidebar.selectbox("X-axis Column", columns, index=x_col_index)
    y_col = st.sidebar.selectbox("Y-axis Column", columns, index=y_col_index)

    x_data = data[x_col].values
    y_data = data[y_col].values

    n_segments = st.sidebar.number_input(
        "Number of Segments",
        min_value=1,
        value=3,
        step=1,
        help="Specify the number of linear segments. A higher number will fit the data more closely but may lead to overfitting."
    )
    min_segment_length = st.sidebar.number_input("Minimum Segment Length", min_value=2, value=2, step=1, help="The minimum number of data points per segment.")

    if st.sidebar.button("Run Analysis"):
        with st.spinner("Fitting piecewise linear model..."):
            try:
                if n_segments > len(x_data):
                    st.error("Number of segments cannot exceed the number of data points.")
                else:
                    pwlf = FastPWLFit(x_data, y_data)
                    pwlf.fit_model(n_segments, min_segment_length=min_segment_length)
                    st.session_state.pwlf = pwlf
                    st.success("Model fitting complete!")
            except ValueError as e:
                st.error(f"Error during model fitting: {e}")

    # --- Main Panel for Display ---
    st.subheader("Data Visualization")
    
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=x_data, 
        y=y_data, 
        mode='markers', 
        name='Raw Data', 
        marker=dict(color='black', size=5)
    ))

    if st.session_state.pwlf:
        pwlf = st.session_state.pwlf
        x_fit = pwlf.x
        y_fit = pwlf.predict(x_fit)
        
        # A color palette for the different line segments
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

        for i in range(len(pwlf.coefs)):
            # Get start and end indices for the segment from the model
            start_idx = pwlf.breakpoints[i] + 1
            end_idx = pwlf.breakpoints[i+1]
            
            # To ensure the plotted lines are continuous, each segment must share a point
            # with the next. We achieve this by starting the plot from the previous breakpoint.
            plot_start_idx = pwlf.breakpoints[i] if i > 0 else start_idx
            
            # Slice the full fitted data to get the data for this segment
            segment_x = x_fit[plot_start_idx : end_idx + 1]
            segment_y = y_fit[plot_start_idx : end_idx + 1]
            
            if len(segment_x) == 0:
                continue

            color = colors[i % len(colors)]
            
            # Add the colored segment to the plot
            fig.add_trace(go.Scatter(
                x=segment_x, 
                y=segment_y, 
                mode='lines', 
                name=f'Segment {i+1}', 
                line=dict(color=color, width=3)
            ))
    
    fig.update_layout(
        xaxis_title=x_col,
        yaxis_title=y_col,
        legend_title="Legend"
    )
    st.plotly_chart(fig, use_container_width=True)

    if st.session_state.pwlf:
        st.subheader("Fit Results")
        pwlf = st.session_state.pwlf

        @st.cache_data
        def get_results_df(_pwlf_model):
            results = []
            for i in range(len(_pwlf_model.coefs)):
                start_idx = _pwlf_model.breakpoints[i] + 1
                end_idx = _pwlf_model.breakpoints[i+1] + 1
                if end_idx > len(_pwlf_model.x):
                    end_idx = len(_pwlf_model.x)
                
                xi = _pwlf_model.x[start_idx:end_idx]
                yi = _pwlf_model.y[start_idx:end_idx]

                if len(xi) == 0:
                    slope, intercept, r2, duration, fragment_length, ssr, sst = [np.nan] * 7
                    start_x, end_x = np.nan, np.nan
                else:
                    y_pred = _pwlf_model.predict(xi)
                    ssr = np.sum((yi - y_pred) ** 2)
                    sst = np.sum((yi - np.mean(yi)) ** 2) if len(yi) > 1 else 0
                    r2 = 1 - ssr / sst if sst != 0 else 1.0 if ssr == 0 else np.nan
                    duration = xi[-1] - xi[0]
                    fragment_length = yi[-1] - yi[0]
                    slope = _pwlf_model.coefs[i][1]
                    intercept = _pwlf_model.coefs[i][0]
                    start_x = xi[0]
                    end_x = xi[-1]

                result = {
                    'Segment': i + 1,
                    'Start Index': start_idx,
                    'End Index': end_idx - 1,
                    'Start X': start_x,
                    'End X': end_x,
                    'Slope': slope,
                    'Intercept': intercept,
                    'R2': r2,
                    'Duration': duration,
                    'Fragment Length': fragment_length,
                    'SSR': ssr,
                    'SST': sst
                }
                results.append(result)
            return pd.DataFrame(results)

        results_df = get_results_df(pwlf)
        st.dataframe(results_df)

        @st.cache_data
        def convert_df_to_csv(df):
            return df.to_csv(index=False).encode('utf-8')

        csv_data = convert_df_to_csv(results_df)
        st.download_button(
            label="Download results as CSV",
            data=csv_data,
            file_name=f'fit_results_{uploaded_file.name.split(".")[0]}.csv',
            mime='text/csv',
        ) 