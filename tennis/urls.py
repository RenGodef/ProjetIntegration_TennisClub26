from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('accueil/', views.accueil, name='accueil'),
    path('changer-password/', views.changer_password, name='changer_password'),
    path('membres/', views.liste_membres, name='liste_membres'),
    path('mes-reservations/', views.mes_reservations, name='mes_reservations'),
    path('mes-reservations/supprimer/<int:reservation_id>/', views.supprimer_reservation, name='supprimer_reservation'),
    path('reserver/', views.faire_reservation, name='faire_reservation'),
    path('profil/', views.modifier_profil, name='modifier_profil'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('gestion/toggle-membre/<str:numero>/', views.toggle_membre, name='toggle_membre'),
    path('gestion/ajouter-membre/', views.ajouter_membre, name='ajouter_membre'),
    path('gestion/supprimer-membre/<str:numero>/', views.supprimer_membre, name='supprimer_membre'),
    path('gestion/ajouter-terrain/', views.ajouter_terrain, name='ajouter_terrain'),
    path('gestion/supprimer-terrain/<int:numero>/', views.supprimer_terrain, name='supprimer_terrain'),
    path('gestion/modifier-membre/<str:numero>/', views.modifier_membre, name='modifier_membre'),
    path('gestion/bloquer-terrain/', views.bloquer_terrain, name='bloquer_terrain'),
    path('gestion/reserver/', views.admin_reserver, name='admin_reserver'),
    path('terrains/', views.liste_terrains, name='liste_terrains'),
    path('ajax/disponibilite/', views.verifier_disponibilite, name='verifier_disponibilite'),
    path('auth/google/', views.google_login, name='google_login'),
    path('auth/google/callback/', views.google_callback, name='google_callback'),
]