"""IndufixProject URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from appApi.views import *
from appApi import views_odoo
from appApi import views_doran_api
from appApi import views_gabriel

urlpatterns = [
    # path('admin/', admin.site.urls),
    # path('auth/', include('rest_framework.urls')),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
    path('register/', register, name='register'),
    path('alterar-senha/', alterar_senha_usuario, name='admin_alterar_senha'),
    path('usuarios/', listar_usuarios, name='listar_usuarios'),
    path('usuarios/<int:user_id>/toggle/', toggle_usuario, name='toggle_usuario'),
    path('usuarios/<int:user_id>/excluir/', excluir_usuario, name='excluir_usuario'),

    path('bitrix/api/v1/', post_bitrix),
    path('bitrix/api/campanha/v1/', api_campanha),
    path('bitrix/api/campanha/v2/', api_campanha_lead),
    path('bitrix/api/altera_vendedor/v1/', api_troca_vendedor_doran),
    path('bitrix/api/consulta_orcamento/<int:pk>/', consulta_orcamento),
    path('bitrix/api/orcamento_html/<int:pk>/', orcamento_html),
    path('integra_nfe/', views_odoo.integra_nfe_odoo),
    path('historico_titulos/', historico_titulos),
    path('doran/api/get_pv_capa/', views_doran_api.get_pv_capa),
    path('doran/api/get_pv_itens/', views_doran_api.get_pv_itens),
    path('doran/api/get_count_pv/', views_doran_api.get_count_pv),
    path('doran/api/get_fornecedores_produto/', views_doran_api.get_fornecedores_produto),
    path('doran/api/get_data_comissao_lider_vendas/', views_doran_api.get_data_comissao_lider_vendas),
    path('doran/api/get_dados_cliente/', views_doran_api.get_dados_cliente),
    path('doran/api/atualizar_dados_orcamento/', views_doran_api.atualizar_dados_orcamento),
    path('doran/api/atualizar_status_nf/', views_doran_api.atualizar_status_nf),
    path('doran/api/atualizar_cadastro_cliente/', views_doran_api.atualizar_cadastro_cliente),
    path('doran/api/atualizar_cadastro_transportadora/', views_doran_api.atualizar_cadastro_transportadora),
    path('doran/api/atualizar_cadastro_fornecedor/', views_doran_api.atualizar_cadastro_fornecedor),
    path('doran/api/atualizar_produto/', views_doran_api.atualizar_produto),
    path('doran/api/atualizar_estoque_itens/', views_doran_api.atualizar_estoque_itens),
    path('doran/recebimento/', pesquisar_pedido, name='pesquisar_pedido'),
    path('doran/recebimento_v2/', pesquisar_pedido_v2, name='pesquisar_pedido_v2'),
    path('doran/recebimento/locais/', lista_locais, name='lista_locais'),
    path('doran/recebimento/conferir/', salvar_conferencia, name='salvar_conferencia'),
    path('doran/recebimento/salvar-fotos/', salvar_fotos, name='salvar_fotos'),
    path('doran/recebimento/carregar-fotos/', carregar_fotos, name='carregar_fotos'),
    path('doran/recebimento/buscar-local/', buscar_local, name='buscar_local'),
    path('doran/recebimento/buscar-dados-item/', buscar_dados_item_oc, name='buscar_dados_item_oc'),
    path('doran/recebimento/salvar-rnc/', salvar_rnc, name='salvar_rnc'),

    path('comissao_vendas/', relatorio_comissao_vendas, name='relatorio_comissao_vendas'),
    path('dashboard_expedicao_2/', views_gabriel.dashboard_expedicao_2, name='dashboard_expedicao_2'),
    # path('testeapi/', main),
    # path('api/v1/cursos/', CursoAPIView.as_view(), name='cursos'),
    # path('api/v1/avaliacoes/', AvaliacaoAPIView.as_view(), name='avaliacoes'),
]
