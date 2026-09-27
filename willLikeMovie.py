import numpy as np
import pandas as pd
from sklearn import tree
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import confusion_matrix , mean_absolute_error , mean_squared_error , r2_score
from sklearn.metrics import classification_report , silhouette_score
from sklearn.model_selection import train_test_split , GridSearchCV
from sklearn.model_selection import cross_val_score
from sklearn.ensemble import RandomForestClassifier , RandomForestRegressor , IsolationForest
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics.pairwise import cosine_similarity
import seaborn as sns
import matplotlib.pyplot as plt
from sklearn.preprocessing import OneHotEncoder , MultiLabelBinarizer , StandardScaler
from sklearn.compose import ColumnTransformer
import ast
import os
from sklearn.cluster import KMeans 
from sqlalchemy import create_engine


pd.set_option('display.max_rows',None)
DB_URL = os.environ.get(
    "WILLLIKEMOVIE_DB_URL",
    "mysql+pymysql://root:1234567@localhost/willlikemovie",
)
engine = create_engine(DB_URL)
def mlb_transformer(df):
    
    
    mlb = MultiLabelBinarizer()
    genre_matrix = mlb.fit_transform(df['genres'])
    genre_names = mlb.classes_
    df_genres = pd.DataFrame(genre_matrix,columns=genre_names,index=df.index)
    df = df.drop('genres',axis=1)
    df = pd.concat([df,df_genres],axis=1)
    return df

#dataset = pd.read_csv('movieforme.csv')
#df = pd.DataFrame(dataset)
df = pd.read_sql("SELECT * FROM movieforme",engine)

scaler = StandardScaler()
categorical_features = ['country']
multilabel_features = ['genres']
scaling_features = ['year','imdb','agerating']
preprocessor = ColumnTransformer(
    transformers=[
        ('cat',OneHotEncoder(handle_unknown='ignore'),categorical_features),
        ('num',scaler,scaling_features)
        
    ],
    remainder='passthrough'
)

kmeans = KMeans(n_clusters=15,init='k-means++',random_state=42)
df['genres']=df['genres'].str.lower()
df['genres']= df['genres'].str.split('|')

df = mlb_transformer(df)

df['country']=df['country'].str.lower()
df['country']=df['country'].str.strip()
#print(df)
titles = df['title']
scores = df['score']
likes = df['like']

df = df.drop(['title'],axis=1)
df = df.drop(['idmovieforme'],axis=1)
x = df.drop(columns=['like','score'])
feature_columns = list(x.columns)

df['like']=df['like'].str.strip()
y_like=df['like']
y_score=df['score']

x=preprocessor.fit_transform(x)


x_train,x_test,y_train,y_test=train_test_split(x,y_like,test_size=0.2)
x_train2,x_test2,y_train2,y_test2=train_test_split(x,y_score,test_size=0.2)
#clf=DecisionTreeClassifier()
clf_like= RandomForestClassifier(n_estimators=200,class_weight='balanced',random_state=42)
clf_score= RandomForestRegressor(n_estimators=200,random_state=42)

model=IsolationForest()


#clf=KNeighborsClassifier()
#param_grid = {
#    'n_estimators':[100,200,300,400,500,600],
#   'max_depth' : [None , 5,10,20],
#    'min_samples_split' : [2,5,10,15,20],
#    'min_samples_leaf' : [1,2,5,10],
#    'max_features' : ['sqrt','log2',0.5,'auto'],
#    'criterion' : ['gini','entropy']
#}
#grid_search = GridSearchCV(estimator=clf,param_grid=param_grid,cv=10,scoring='accuracy',n_jobs=-1)
#print("running grid search...")
#grid_search.fit(x_train,y_train)
#print("grid search ended")
#print(f"best hyperparameters : {grid_search.best_params_}")
#print(f"best accuracy : {grid_search.best_score_:.4f}")

#clf.fit(x_train,y_train)

#clf_score.fit(x_train2,y_train2)
clf_score.fit(x,y_score)
clf_like.fit(x,y_like)

model.fit(x)
kmeans.fit(x)
pred=model.predict(x)
print(f"anomaly : {pred}")
y_pred=clf_like.predict(x_test)
y_pred2=clf_score.predict(x_test2)
print(f"y_pred2 : {y_pred2}")
print(f"y_test2 : {y_test2}")
df['cluster']=kmeans.labels_
df['title']=titles
df['score']= scores
df['like']=likes
df.to_csv('movieforme_cluster.csv',index=False)
#print(y_test==y_pred)
#confusion_matrix(y_test,y_pred)
#print(classification_report(y_test,y_pred))
scores=cross_val_score(clf_like,x,y_like,cv=10,scoring='accuracy')

mae_scores = cross_val_score(clf_score,x,y_score,cv=10,scoring='neg_mean_absolute_error')
r2_scores = cross_val_score(clf_score,x,y_score,cv=10,scoring='r2')

mean_mae = -np.mean(mae_scores)
mean_r2 = np.mean(r2_scores)

print("scores for each fold:",scores)
print(f"average accuracy: {np.mean(scores)}")

data={
    'genres':[['psychological-drama','psychological-thriller','mystery','crime','drama','sci-fi','thriller'],['adult-animation','political-drama','psychological-thriller','dystopian', 'post-apocalyptic','superhero','action','fantasy','drama','slice-of-life', 'crime', 'historical', 'musical', 'short', 'romance', 'anime', 'thriller', 'psychological-drama', 'coming-of-age', 'sport', 'animation', 'war', 'classic', 'mystery', 'black-comedy', 'biography', 'psychological', 'horror', 'children', 'teen-drama','family', 'sci-fi', 'adventure', 'comedy']],
    'year':[2023,2019],
    'imdb':[8.1,8.4],
    'country':['usa','usa'],
    'agerating':[18,12]
    
    }
data = pd.DataFrame(data)
data = mlb_transformer(data)
data = data.reindex(columns=feature_columns, fill_value=0)
data=preprocessor.transform(data)
y_pred_new= clf_like.predict(data)
y_pred_new_score= clf_score.predict(data)

print(y_pred_new)
print(y_like.value_counts())
#probabilities = clf.predict_proba(x_test)
#print(probabilities)
probab = clf_like.predict_proba(data)
print(probab)
#sns.pairplot(df,hue='like',palette='viridis')
#plt.suptitle('pair plot of features ',y=1.02)
#plt.show()
mae = mean_absolute_error(y_test2,y_pred2)
mse = mean_squared_error(y_test2,y_pred2)
rmse = np.sqrt(mse)
r2=r2_score(y_test2,y_pred2)
#print(f"MAE : {mae:.4f}")
#print(f"MSE : {mse:.4f}")
#print(f"RMSE : {rmse:.4f}")
#print(f"R-squared : {r2:.4f}")
print(f"predicted score :{y_pred_new_score}")
print(f"mae mean: {mean_mae:.2f}")
print(f"r2 mean :{mean_r2:.2f}")

sil_score = silhouette_score(x,kmeans.labels_)
print(f"silhouette score : {sil_score}")
new_cls = kmeans.predict(data)
print(f"new data's cluster : {new_cls}")
df.to_csv('movieforme_cluster.csv')
df_score = df.drop(columns=['like','country','title','cluster'])


correlation_matrix = df_score.corr(method='spearman')
target_corr = correlation_matrix['score'].drop('score')
sorted_target_corr = target_corr.abs().sort_values(ascending=False)
print(f"correlation with score :{sorted_target_corr}")
similarity_matrix = cosine_similarity(x)
print(similarity_matrix)
similarity_matrix_1 = similarity_matrix[13]
print(similarity_matrix_1)