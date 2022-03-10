import streamlit as st
import ee
import geemap
import geemap.foliumap as fmap
import geopandas as gpd
import pandas as pd
import numpy as np
import time
from datetime import datetime, date, timedelta
from shapely.geometry import Polygon
import os
import altair as alt
import folium
import rasterio as rio

import pickle
import joblib
from sklearn import preprocessing
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix

import zipfile
import requests
import urllib.request
import random
from matplotlib import colors
import matplotlib.pyplot as plt


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def loadData():
    """
    Loads fire data and caches with streamlit
    """
    fires = gpd.read_file("data/norCalFires.geojson")
    fires["Start"] = fires["Start"].apply(lambda x: date.fromisoformat(x))
    fires["End"] = fires["End"].apply(lambda x: date.fromisoformat(x))
    # fires["geometry"] = fires["geometry"].apply(lambda x: bbox(x.bounds))
    return fires


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def loadModels():
    """
    Stores trained models in a dictionary and caches with streamlit
    """
    models = dict()

    models["Logistic Regression"] = pickle.load(open("models/logistic_regression.sav", 'rb'))
    models["Multi-Layer Perceptron"] = pickle.load(open("models/mlp.sav", 'rb'))
    models["Random Forest"] = joblib.load(open("models/rf.pkl", 'rb'))
    models["SVM"] = joblib.load(open("models/svc.pkl", "rb"))
    models["log_boost"] = joblib.load(open("models/log_boost.pkl", "rb"))
    models["Boosted Trees"] = joblib.load(open("models/tree_boost.pkl", "rb"))

    # etcURL = "https://www.dl.dropboxusercontent.com/s/jr8vwvz1tsee1f9/etc.pkl?dl=0"
    # etcRequest = requests.get(etcURL, allow_redirects=True)
    # open("extraTrees.pkl", "wb").write(etcRequest.content)
    # del etcURL
    # models["Extra Trees"] = joblib.load(open("extraTrees.pkl", 'rb'))

    return models


# @st.cache(allow_output_mutation=True, suppress_st_warning=True)
def loadDrawMap():
    """
    Creates a folium map with overlay of California counties and caches with streamlit
    """
    drawMap = fmap.Map(add_google_map=False,
                       basemap="HYBRID",
                       plugin_Draw=True,
                       draw_export=True,
                       locate_control=True,
                       plugin_LatLngPopup=False)

    drawMap.set_center(-121.15, 40.25, 6.5)

    # drawMap.add_shapefile(in_shp="data/CA_Counties/CA_Counties_TIGER2016.shp",
    #                       layer_name="CA Counties (no tooltips)",
    #                       smooth_factor=2,
    #                       highlight_function=lambda x: {"weight": 4,
    #                                                     "color": "#FF5699"},
    #                       style_function=lambda feature: {"fillColor": feature["properties"]["NAME"],
    #                                                       "color" : "#FFB3D1",
    #                                                       "weight" : 1,
    #                                                       "fillOpacity" : 0})
    #
    # drawMap.add_shapefile(in_shp="data/CA_Counties/CA_Counties_TIGER2016.shp",
    #                       layer_name="CA Counties",
    #                       smooth_factor=2,
    #                       highlight_function=lambda x: {"weight": 4,
    #                                                     "color": "#FF5699"},
    #                       tooltip=folium.features.GeoJsonTooltip(fields=["NAME"],
    #                                                              aliases=["County:"],
    #                                                              labels=True,
    #                                                              sticky=True,
    #                                                              toLocaleString=True),
    #                       style_function=lambda feature: {"fillColor": feature["properties"]["NAME"],
    #                                                       "color" : "#FFB3D1",
    #                                                       "weight" : 1,
    #                                                       "fillOpacity" : 0})

    return drawMap.to_streamlit(height=500, width=500)


def updateIdState(fireID):
    """
    Update app
    """
    st.session_state['idLst'].append(fireID)
    st.session_state['currentIndex'] += 1

    return st.session_state['idLst'], st.session_state['currentIndex']


def updateWidgetState(widgets):
    """
    """
    st.session_state["widgetState"].append(np.array(widgets))
    st.session_state["currentState"] += 1

    return st.session_state["widgetState"], st.session_state["currentState"]


def bbox(x):
    """
    Creates a bounding box over a geometry object

    Args:
        x: GeoPandas geometry object

    Returns:
        Shapely.Polygon that represents buffered bounding box over input geometry
    """
    minx, miny, maxx, maxy = x
    coords = ((minx, miny), (minx, maxy), (maxx, maxy), (maxx, miny))
    return Polygon(coords)


def convertDate(date):
    """
    Converts EE.Date or unix date (in milliseconds) to Y-M-D formst
    """
    if isinstance(date, ee.Date):
        date = date.getInfo()["value"]

    return datetime.utcfromtimestamp(date/1000).strftime("%Y-%m-%d")# %H:%M:%S')


def formatFireSelectBox(data):
    """

    """
    return {k: "{} ({})".format(v1, v2) for k, v1, v2 in data[["ID", "Fire", "Year"]].sort_values(by="Fire").values}


def subsetFires(data, startYear, endYear, containedMonths, sizeClass, counties):
    """
    Subsets fire data based on user defined query parameters
    """
    if startYear == endYear:
        st.error("### Select valid time interval")
    else:
        subset = data[(data["Year"] >= startYear) & (data["Year"] < endYear)]

    if len(containedMonths) > 0:
        subset = subset[subset["Contained Month"].isin(containedMonths)]

    if len(sizeClass) > 0:
        subset = subset[subset["Size Class"].isin(sizeClass)]

    if len(counties) > 0:
        subset = subset[subset["County"].isin(counties)]

    return subset.sort_values(by="Fire").reset_index(drop=True)


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def uploaded_file_to_gdf(data):
    """
    Source: https://github.com/giswqs/streamlit-geospatial/blob/master/apps/timelapse.py
    """
    import tempfile
    import os
    import uuid

    _, file_extension = os.path.splitext(data.name)
    file_id = str(uuid.uuid4())
    file_path = os.path.join(tempfile.gettempdir(), f"{file_id}{file_extension}")

    with open(file_path, "wb") as file:
        file.write(data.getbuffer())

    if file_path.lower().endswith(".kml"):
        gpd.io.file.fiona.drvsupport.supported_drivers["KML"] = "rw"
        gdf = gpd.read_file(file_path, driver="KML")
    else:
        gdf = gpd.read_file(file_path)

    return gdf.to_crs("EPSG:4326")


def prepImages(geometry, startDate, endDate):
    if endDate-startDate >= timedelta(days=90):
        shiftedDate = ee.Date((endDate - timedelta(days=60)).isoformat())
        endDate += timedelta(days=20)
    elif endDate-startDate >= timedelta(days=60):
        shiftedDate = ee.Date((endDate - timedelta(days=40)).isoformat())
        endDate += timedelta(days=30)
    else:
        shiftedDate = ee.Date((endDate + timedelta(days=1)).isoformat())
        endDate += timedelta(days=60)


    if type(geometry) is gpd.geoseries.GeoSeries:
        geometry = gpd.GeoDataFrame(geometry=gpd.GeoSeries(geometry))
    if type(startDate) is date:
        startDate = startDate.isoformat()
    if type(endDate) is date:
        endDate = endDate.isoformat()

    geometry_EE = ee.Geometry(geemap.gdf_to_ee(geometry).first().geometry())

    startDate, endDate = ee.Date(startDate), ee.Date(endDate)

    preFireImage = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"
                    ).filterDate(startDate.advance(-60, "day"), startDate
                    ).filterBounds(geometry_EE
                    ).filter(ee.Filter.lte("CLOUD_COVER", 10)
                    ).mean(
                    ).clip(geometry_EE)

    postFireImage = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"
                     # ).filterDate(endDate.advance(1, "day"), endDate.advance(60, "day")
                     ).filterDate(shiftedDate, endDate
                     ).filterBounds(geometry_EE
                     ).filter(ee.Filter.lte("CLOUD_COVER", 15)
                     ).mean(
                     ).clip(geometry_EE)

    # Calculate NBR, dNBR, and burn severity
    preFireNBR = preFireImage.normalizedDifference(['SR_B5', 'SR_B7'])
    postFireNBR = postFireImage.normalizedDifference(['SR_B5', 'SR_B7'])
    dNBR = (preFireNBR.subtract(postFireNBR)
                     ).multiply(1000
                     ).rename("dNBR")

    burnSeverity = dNBR.expression(" (b('dNBR') > 425) ? 5 "    # purple: high severity
                                   ":(b('dNBR') > 225) ? 4 "    # orange: moderate severity
                                   ":(b('dNBR') > 100) ? 3 "    # yellow: low severity
                                   ":(b('dNBR') > -60) ? 2 "    # green: unburned/unchanged
                                   ":(b('dNBR') <= -60) ? 1 "   # brown: vegetation growth
                                   ":0"                         # pseudo mask
                      ).rename("burnSeverity")

    # Get SRTM elevation, NLCD land coverpostFireImageNDVI, and GRIDMET weather
    dem = ee.Image("NASA/NASADEM_HGT/001").select("elevation")

    nlcd = ee.ImageCollection('USGS/NLCD_RELEASES/2016_REL'
               ).filter(ee.Filter.eq('system:index', '2016')).first()

    lc = nlcd.select("landcover"
            ).expression(" (b('landcover') > 90) ? 1 "    # blue: other (wetland)
                         ":(b('landcover') > 80) ? 6 "    # brown: agriculture
                         ":(b('landcover') > 70) ? 5 "    # lightGreen: grassland/herbaceous
                         ":(b('landcover') > 50) ? 4 "    # yellow: shrub
                         ":(b('landcover') > 40) ? 3 "    # green: forest
                         ":(b('landcover') > 30) ? 1 "    # blue: other (barren land)
                         ":(b('landcover') > 20) ? 2 "    # red: developed/urban
                         ":(b('landcover') > 10) ? 1 "    # blue: other (water/perennial ice+snow)
                         ":0"                             # handle for potential exceptions
            ).rename("landCover")


    lcViz = ee.ImageCollection('USGS/NLCD_RELEASES/2016_REL'
             ).filter(ee.Filter.eq('system:index', '2011')
             ).first(
             ).select("landcover"
             ).expression(" (b('landcover') > 90) ? 1 "    # blue: other (wetland)
                          ":(b('landcover') > 80) ? 6 "    # brown: agriculture
                          ":(b('landcover') > 70) ? 5 "    # lightGreen: grassland/herbaceous
                          ":(b('landcover') > 50) ? 4 "    # yellow: shrub
                          ":(b('landcover') > 40) ? 3 "    # green: forest
                          ":(b('landcover') > 30) ? 1 "    # blue: other (barren land)
                          ":(b('landcover') > 20) ? 2 "    # red: developed/urban
                          ":(b('landcover') > 10) ? 1 "    # blue: other (water/perennial ice+snow)
                          ":0"                             # handle for potential exceptions)
             ).clip(geometry_EE
             ).rename("landCoverViz")

    ndvi = postFireImage.normalizedDifference(["SR_B5", "SR_B4"]
                       ).rename("NDVI"
                       ).multiply(1000)

    # Merge all image bands together
    combined = postFireImage.select('SR_B.'          # post-fire L8 bands 1-7
                           ).addBands(burnSeverity   # classified burn severity
                           ).addBands(dNBR           # dNBR
                           ).addBands(ndvi           # post-fire NDVI
                           ).addBands(dem            # SRTM elevation
                           ).addBands(nlcd.select("percent_tree_cover")
                           ).addBands(lc             # simplified landCover for model
                           ).addBands(lcViz)         # simplified landCover for viz

    # Update session state with queried ee objects
    st.session_state["eeObjects"] = [preFireImage, postFireImage, combined, geometry_EE]
    return st.session_state["eeObjects"]


def ee_export_image(image, filename, scale, region, crs=None):
    """Exports an ee.Image as a GeoTIFF.

    Args:
        image (object): The ee.Image to download.
        filename (str): Output filename for the exported image.
        scale (float, optional): A default scale to use for any bands that do not specify one; ignored if crs and crs_transform is specified. Defaults to None.
        crs (str, optional): A default CRS string to use for any bands that do not explicitly specify one. Defaults to None.
        region (object, optional): A polygon specifying a region to download; ignored if crs and crs_transform is specified. Defaults to None.
        file_per_band (bool, optional): Whether to produce a different GeoTIFF per band. Defaults to False.
    """

    filename = os.path.abspath(filename)
    basename = os.path.basename(filename)
    name = os.path.splitext(basename)[0]
    filename_zip = filename.replace(".tif", ".zip")

    try:
        print("Generating URL...")
        params = {"name": name,
                  "filePerBand": False,
                  "scale": scale,
                  "region": region}

        if crs is not None:
            params["crs"] = crs

        try:
            url = image.getDownloadURL(params)
        except Exception as e:
            print("An error occurred while downloading.")
            print(e)
            return
        print(f"Downloading data from {url}\nPlease wait...")
        r = requests.get(url, stream=True)

        if r.status_code != 200:
            print("An error occurred while downloading.")
            return

        with open(filename_zip, "wb") as fd:
            for chunk in r.iter_content(chunk_size=1024):
                fd.write(chunk)

    except Exception as e:
        print("An error occurred while downloading.")
        print(r.json()["error"]["message"])
        return

    try:
        with zipfile.ZipFile(filename_zip) as z:
            z.extractall(os.path.dirname(filename))
        os.remove(filename_zip)
    except Exception as e:
        print(e)


def downloadRaster(imgScale, image, geometry):
    """
    Downloads an ee.Image as a raster at a given spatial resolutions over an ee.Geometry
    """
    try:
        image.bandNames().size().getInfo()
    except Exception as e:
        st.error("### No suitable Landsat images are available. Please try again with a different fire.")
        st.stop()
        return

    startTime = time.time()
    numTries = len(imgScale)
    for i in range(numTries):
        try:
            ee_export_image(image=image,
                            filename="raster.tif",
                            scale=imgScale[i],
                            region=geometry)
            if "raster.tif" in os.listdir():
                break
        except Exception:
            continue

    if "raster.tif" not in os.listdir():
        st.error("### Fire exceeds total request size. Please try again with a smaller fire.")
        st.stop()
    else:
        colNames = ['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7',
                    'burnSeverity','dNBR','NDVI','elevation',
                    'percent_tree_cover','landCover','landCoverViz']

        colNames = {index:value for index, value in enumerate(colNames)}

        img, data = rio.open("raster.tif"), {}
        st.session_state["rasterDims"] = [img.height, img.width]
        img = img.read()
        for index, val in colNames.items():
            data[val] = img[index].flatten()

        # Convert to df, impute NA with mean + random value for burnSeverity == 0 (unlikely)
        df = pd.DataFrame(data)
        df = df.fillna(df.mean()).reset_index(drop=True).round(2)

        # catches possible exceptions where null pixels lead to burnSeverity == 0
        num = sum(df["burnSeverity"] <= 0)
        if num > 0:
            imputeValues = [random.sample([1,2,3,4,5], k=1)[0] for i in range(num)]
            df.loc[df["burnSeverity"] <= 0, "burnSeverity"] = imputeValues

        df.astype(int).to_parquet("raster.parquet")
        # df.to_parquet("raster.parquet")


def burnSeverityImage(data, dim, fileName):
    """
    Produces a burn severity image from raster data using matplotlib.

    Args:
        data: raster data
        dim: height and width of output image
    """
    cmapDict = {1:'#706C1E', 2:'#4E9D5C', 3:'#FFF70B', 4:'#FF641B', 5:'#A41FD6'}

    # remapped cmap for issue with oscar's models
    cmap = colors.ListedColormap([cmapDict[i] for i in sorted(set(data))])
    height, width = dim
    image = plt.imshow(data.reshape(height, width), cmap=cmap)
    plt.axis("off")
    plt.savefig(fileName, transparent=True, bbox_inches='tight', pad_inches=0)


def add_legend(map, legend_dict=None, opacity=1.0):
    """
    Adds a dual map legend to folium map.
    Source: https://geemap.org/foliumap/#geemap.foliumap.Map.add_legend

    Args:
        title (str, optional): Title of the legend. Defaults to 'Legend'. Defaults to "Legend".
        colors ([type], optional): A list of legend colors. Defaults to None.
        labels ([type], optional): A list of legend labels. Defaults to None.
        legend_dict ([type], optional): A dictionary containing legend items as keys and color as values. If provided, legend_keys and legend_colors will be ignored. Defaults to None.
        builtin_legend ([type], optional): Name of the builtin legend to add to the map. Defaults to None.
        opacity (float, optional): The opacity of the legend. Defaults to 1.0.

    """
    from branca.element import MacroElement, Template

    legend_template = os.path.join("legendTemplate.txt")

    if legend_dict is not None:
        if not isinstance(legend_dict, dict):
            raise ValueError("The legend dict must be a dictionary.")
        else:
            labels = list(legend_dict.keys())
            colors = list(legend_dict.values())
            colors = ["#" + color for color in colors]

    content = []
    noneCount = 0
    with open(legend_template) as f:
        lines = f.readlines()
        for index, line in enumerate(lines):
            if index <= 36:
                content.append(line)
            elif index < 39:
                content.append(line)
            elif index == 39:
                for i, color in enumerate(colors):
                    if color == "#None":
                        noneCount += 1
                        if noneCount == 2:
                            content.append("<div class='legend-title'><br>{}</div>".format(labels[i]))
                        else:
                            content.append("<div class='legend-title'>{}</div>".format(labels[i]))
                    else:
                        item = f"    <li><span style='background:{color};opacity:{opacity};'></span>{labels[i]}</li>\n"
                        content.append(item)
            elif index > 41:
                content.append(line)

    template = "".join(content)
    macro = MacroElement()
    macro._template = Template(template)

    return map.get_root().add_child(macro)


def prepData(data):
    """
    """
    scaler = preprocessing.StandardScaler().fit(data.values)
    return scaler.transform(data)


def modelMetrics(labels, predictions):
    """
    Returns a confusion matrix and table with precision, recall, and f1 scores.

    Args:
        labels: array of burn severity values generated with a linear dNBR threshold
        predictions: array of predicted burn severity values
    """
    cm = confusion_matrix(labels, predictions)
    predictedTotal = np.sum(cm, axis = 0)
    actualTotal = list(np.sum(cm, axis = 1)) + [None]

    precision = np.diag(cm) / np.sum(cm, axis = 0)
    recall = np.diag(cm) / np.sum(cm, axis = 1)
    f1 = np.round(100*(2*(precision * recall) / (precision + recall)), 2)

    precision = np.round(100*precision, 2)
    recall = np.round(100*recall, 2)

    cm = np.vstack((cm, predictedTotal))
    cm = np.hstack((cm, np.array(actualTotal).reshape(len(actualTotal),1)))

    cm = pd.DataFrame(cm)

    bsMap = {1: "Vegetation Growth", 2: "Unburned", 3: "Low", 4: "Moderate", 5: "High"}
    columns = [bsMap[i] for i in range(1, len(cm.columns[:-1])+1)]
    index = [bsMap[i] for i in range(1, len(cm.index[:-1])+1)]

    cm.columns = columns + ["Predicted Total"]
    cm.index = index + ["Actual Total"]

    metrics = pd.DataFrame({"Precision (%)": precision, "Recall (%)": recall, "F1 (%)": f1})
    metrics.index = index

    return cm.fillna(0), metrics.fillna(0)


def sidebarContactInfo():
    st.write(
    """
    <ul>
        <li style="font-size:15px";>
            <b>Alice Lu</b>
            &nbsp;&nbsp;
            <a href='mailto:anchi@ucsd.edu' style='color: transparent;'>
                <img src='https://cdn.iconscout.com/icon/free/png-256/email-2026367-1713640.png' alt='email icon' align='middle' style='width:20;height:20px;'>
            </a>
            &nbsp;
            <a href='https://www.youtube.com/' style='color: transparent;'>
                <img src='https://cdn-icons-png.flaticon.com/512/174/174857.png' alt='linkedin icon' align='middle' style='width:17;height:15px;'>
            </a>
        </li>
        <li style="font-size:15px";>
            <b>Anthony Chi (Author)</b>
            &nbsp;&nbsp;
            <a href='mailto:anchi@ucsd.edu' style='color: transparent;'>
                <img src='https://cdn.iconscout.com/icon/free/png-256/email-2026367-1713640.png' alt='email icon' align='middle' style='width:20;height:20px;'>
            </a>
            &nbsp;
            <a href='https://www.youtube.com/' style='color: transparent;'>
                <img src='https://cdn-icons-png.flaticon.com/512/174/174857.png' alt='linkedin icon' align='middle' style='width:17;height:15px;'>
            </a>
        </li>
        <li style="font-size:15px";>
            <b>Oscar Jimenez</b>
            &nbsp;&nbsp;
            <a href='mailto:anchi@ucsd.edu' style='color: transparent;'>
                <img src='https://cdn.iconscout.com/icon/free/png-256/email-2026367-1713640.png' alt='email icon' align='middle' style='width:20;height:20px;'>
            </a>
            &nbsp;
            <a href='https://www.youtube.com/' style='color: transparent;'>
                <img src='https://cdn-icons-png.flaticon.com/512/174/174857.png' alt='linkedin icon' align='middle' style='width:17;height:15px;'>
            </a>
        </li>
        <li style="font-size:15px";>
            <b>Jaskaranpal Singh</b>
            &nbsp;&nbsp;
            <a href='mailto:anchi@ucsd.edu' style='color: transparent;'>
                <img src='https://cdn.iconscout.com/icon/free/png-256/email-2026367-1713640.png' alt='email icon' align='middle' style='width:20;height:20px;'>
            </a>
            &nbsp;
            <a href='https://www.youtube.com/' style='color: transparent;'>
                <img src='https://cdn-icons-png.flaticon.com/512/174/174857.png' alt='linkedin icon' align='middle' style='width:17;height:15px;'>
            </a>
        </li>
    </ul>
    """,
    unsafe_allow_html=True)


def altChart(data):
    """

    """
    # bsMap = {1: "Vegetation Growth", 2: "Unburned", 3: "Low", 4: "Moderate", 5: "High"}
    lcMap = {1: "Other", 2: "Developed", 3: "Forest", 4: "Shrub", 5: "Grassland", 6: "Agriculture"}

    # bsPivot = data.pivot_table(index="burnSeverity",
    #                            values="SR_B1",
    #                            aggfunc=len
    #              ).reset_index(
    #              ).sort_values(by="burnSeverity"
    #              ).rename(columns={"burnSeverity": "Burn Severity",
    #                                "SR_B1": "Percentage"})
    # bsPivot["Percentage"] /= bsPivot["Percentage"].sum()
    # bsPivot["Percentage"] = (100*bsPivot["Percentage"]).round(2)
    # bsPivot["Burn Severity"] = bsPivot["Burn Severity"].apply(lambda x: bsMap[x])

    lcPivot = data.pivot_table(index="landCoverViz",
                               values="SR_B1",
                               aggfunc=len
                 ).reset_index(
                 ).sort_values(by="landCoverViz"
                 ).rename(columns={"landCoverViz": "Land Cover",
                                   "SR_B1": "Percentage"})
    lcPivot["Percentage"] /= lcPivot["Percentage"].sum()
    lcPivot["Percentage"] = (100*lcPivot["Percentage"]).round(2)
    lcPivot["Land Cover"] = lcPivot["Land Cover"].apply(lambda x: lcMap[x])


    # bsChart = alt.Chart(bsPivot
    #             ).mark_bar(
    #             ).encode(x=alt.X("Percentage:Q",
    #                              title=" "),
    #                      y=alt.Y("Burn Severity:O",
    #                              title=" ",
    #                              sort=list(bsMap.values())),
    #                      color=alt.Color("Burn Severity",
    #                                      legend=None,
    #                                      scale=alt.Scale(domain=list(bsMap.values()),
    #                                                      range=["rgb(112,108,30)", "rgb(78,157,92)",
    #                                                             "rgb(255,247,11)", "rgb(255,100,27)",
    #                                                             "rgb(164,31,214)"])),
    #                      tooltip=["Burn Severity", "Percentage"]
    #             ).properties(title="Burn Severity (%)")

    lcChart = alt.Chart(lcPivot
                ).mark_bar(
                ).encode(x=alt.X("Percentage:Q",
                         title=" "),
                         y=alt.Y("Land Cover:O",
                                 title=" ",
                                 sort=list(lcMap.values())),
                         color=alt.Color("Land Cover",
                                         legend=None,
                                         scale=alt.Scale(domain=list(lcMap.values()),
                                                         range=["rgb(162,214,242)", "rgb(255,127,104)",
                                                                "rgb(37,137,20)", "rgb(255,241,0)",
                                                                "rgb(123,216,96)", "rgb(185,155,86)"])),
                         tooltip=["Land Cover", "Percentage"]
                ).properties(title="Land Cover (%)")

    # return bsChart, lcChart
    return lcChart
