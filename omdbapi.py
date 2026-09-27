import pandas as pd
import requests
import sys
import os
import re
sys.stdout.reconfigure(encoding="utf-8")
# Keep the key out of the repository: set OMDb_API_KEY in the environment.
API_KEY = os.environ.get("OMDB_API_KEY", "")
if not API_KEY:
    print("set the OMDb_API_KEY environment variable, for example:")
    print('  set OMDb_API_KEY=your_key_here')
movies_enriched_df = pd.DataFrame(columns=["Title","Year","Rated","Released","Runtime",
                                        "Genre","Director","Writer","Actors","Plot",
                                        "Language","Country","Awards","Poster","Ratings","Metascore",
                                        "imdbRating","imdbVotes","imdbID","Type","totalSeasons",
                                        "Response"])
def get_movie_info(title,year,df_enriched):
    
    url = "https://www.omdbapi.com/"
    params = {
    "apikey":API_KEY,
    "t":title,
    "year":year
    }
    response = requests.get(url,params=params)

    data = response.json()
    if data["Response"]=="False":
        print("could not find the movie")
        print(response.url)
        print(response.status_code)
        print(response.text)
        return
    
    
    print(f"{data.get('Title')} ({data.get('Year')})")
    #print(data)
    df_enriched.loc[len(df_enriched)]= data
    
#df = pd.DataFrame(data["data"])



dataset = pd.read_csv('movieforme.csv')
df = pd.DataFrame(dataset)

def create_enriched_df(df,title_column,year_column):
    for index,row in df.iterrows():
        movie_name = row[title_column]
        movie_year = row[year_column]
        get_movie_info(movie_name,movie_year,movies_enriched_df)
def split_title_year(text):
    match = re.match(r"^(.*)\s+\((\d{4})\)$",text)
    if match:
        title =match.group(1).strip()
        year = int(match.group(2))
        return title , year
    return text , None


#movies_enriched_df.to_csv("moviesfromapi.csv")
#dataset_ = pd.read_csv('moviesfromapi.csv')
#dfP = pd.DataFrame(dataset)
dataset_items = pd.read_csv('items.csv',sep="|")
df_items = pd.DataFrame(dataset_items)
df_items[['movie_name','year']] = df_items['movie_title'].apply(
    lambda x:pd.Series(split_title_year(x))
)
#df_items.to_csv('items_version2.csv')
#print(f"{df_items['movie_name']} + {df_items['year']}")
#create_enriched_df(df_items,'movie_name','year')
#print(movies_enriched_df)
df_ratings = pd.read_csv('ratings.csv',sep="\s+",header=None)
df_ratings.columns=['user_id','item_id','rating','timestamp']
df_ratings.to_csv('ratings_clean.csv',sep=',',index=False)

