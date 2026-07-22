from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('wizard/start', views.wizard_start, name='wizard_start'),
    path('wizard/<int:step>', views.wizard_step, name='wizard_step'),
    path('result', views.result, name='result'),
    path('restart', views.restart, name='restart'),
]
