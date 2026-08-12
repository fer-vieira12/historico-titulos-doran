from time import sleep

from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib import messages
from django.shortcuts import render, redirect
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import HttpResponse, JsonResponse
from django.db import connections, connection, transaction
from django.views.decorators.csrf import csrf_exempt
from .indufix_api import OdooIndufix
from .views_orcamentos_perdidos import Orcamentos
from .forms import RelatorioComissaoVendasForm
from .models import Vendedor
from datetime import *
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
import logging

_logger = logging.getLogger(__name__)
from PIL import Image
from io import BytesIO

import base64
import json
import locale
import requests
import logging
import datetime
import xmlrpc
import xmlrpc.client

locale.setlocale(locale.LC_ALL, '')
logger = logging.getLogger(__name__)



@login_required
def listar_usuarios(request):
    usuarios = User.objects.all().order_by('is_active', 'username')
    return render(request, 'listar_usuarios.html', {'usuarios': usuarios})

@login_required
def toggle_usuario(request, user_id):
    try:
        usuario = User.objects.get(id=user_id)
        usuario.is_active = not usuario.is_active
        usuario.save()
        status = "ativado" if usuario.is_active else "desativado"
        messages.success(request, f'Usuário {usuario.username} {status} com sucesso!')
    except User.DoesNotExist:
        messages.error(request, 'Usuário não encontrado!')
    return redirect('listar_usuarios')

@login_required
def excluir_usuario(request, user_id):
    try:
        usuario = User.objects.get(id=user_id)
        username = usuario.username
        usuario.delete()
        messages.success(request, f'Usuário {username} excluído com sucesso!')
    except User.DoesNotExist:
        messages.error(request, 'Usuário não encontrado!')
    return redirect('listar_usuarios')
def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Loga automaticamente após o cadastro
            return redirect('/doran/recebimento/')
    else:
        form = UserCreationForm()

    return render(request, 'register.html', {'form': form})

def alterar_senha_usuario(request):
    context = {}
    if request.method == 'POST':
        username = request.POST.get('username')
        nova_senha = request.POST.get('nova_senha')
        try:
            user = User.objects.get(username=username)
            user.set_password(nova_senha)
            user.save()
            context['mensagem'] = f"Senha do usuário '{username}' alterada com sucesso!"
        except User.DoesNotExist:
            context['erro'] = f"Usuário '{username}' não encontrado."
    return render(request, 'admin_alterar_senha.html', context)

def historico_titulos(request, template_name="historico_titulos.html"):
    context = {}

    if request.method == "POST":
        try:
            id_cliente = request.POST.get("cliente-id", "").strip()
            cnpj_cliente = request.POST.get("cnpj", "").strip()

            with connections['doran'].cursor() as cursor:
                # Construir a query dinamicamente baseado nos parâmetros fornecidos
                query = """ 
                        SELECT 
                        NUMERO_NF_SAIDA,
                        RTRIM (TB_CLIENTE.NOMEFANTASIA_CLIENTE) AS NOMEFANTASIA_CLIENTE,
                        CONVERT (DATE, DATA_LANCAMENTO) AS DATA_LANCAMENTO,
                        CONVERT (DATE, DATA_VENCIMENTO) AS DATA_VENCIMENTO,
                        CONVERT (DATE, DATA_PAGAMENTO) AS DATA_PAGAMENTO,
                        CAST (HISTORICO AS NVARCHAR(MAX)) AS HISTORICO,
                        CONVERT (FLOAT, VALOR_TOTAL) AS VALOR_TOTAL
                        FROM TB_FINANCEIRO (NOLOCK)
                        JOIN TB_CLIENTE (NOLOCK) ON TB_CLIENTE.ID_CLIENTE = TB_FINANCEIRO.CODIGO_CLIENTE
                        WHERE 1=1
                        """
                
                params = []
                
                # Se tem ID do cliente, adiciona à query
                if id_cliente:
                    query += " AND TB_FINANCEIRO.CODIGO_CLIENTE = %s"
                    params.append(int(id_cliente))
                
                # Se tem CNPJ, adiciona à query
                if cnpj_cliente:
                    query += " AND TB_CLIENTE.CNPJ_CLIENTE = %s"
                    params.append(cnpj_cliente)
                
                query += " ORDER BY CONVERT (DATE, DATA_LANCAMENTO) ASC"

                cursor.execute(query, params)
                records = cursor.fetchall()

                dados = []
                for record in records:
                    values = {}
                    values["numero_nf_saida"] = record[0]
                    values["nomefantasia_cliente"] = record[1]
                    values["data_lancamento"] = record[2]
                    values["data_vencimento"] = record[3]
                    values["data_pagamento"] = record[4]
                    values["historico"] = record[5]
                    values["valor_total"] = locale.currency(record[6], grouping=True)
                    
                    dados.append(values)

                context = {
                    "records": dados,
                    "cnpj": cnpj_cliente,
                    "id_cliente": id_cliente
                }

        except ValueError as e:
            _logger.error(f"ID do cliente inválido (deve ser numérico): {str(e)}", exc_info=True)
            context["erro"] = "ID do cliente deve ser um número"
        except Exception as e:
            _logger.error(f"Erro ao consultar histórico de títulos: {str(e)}", exc_info=True)
            context["erro"] = f"Erro ao consultar histórico de títulos: {str(e)}"
    
    return render(request, template_name, context)

    

# Relatório de Comissão de Vendas
def relatorio_comissao_vendas(request):
    if request.method == 'POST':
        form = RelatorioComissaoVendasForm(request.POST)
        if form.is_valid():
            data_inicial = form.cleaned_data['data_inicial']
            data_final = form.cleaned_data['data_final']
            vendedor_data = form.cleaned_data['vendedor']
            vendedor_id, vendedor_nome = vendedor_data.split('|')
            vendedor_nome = vendedor_nome.title()
            
            # Gerar o PDF após relatório ser salvo
            return gerar_relatorio(request, data_inicial, data_final, vendedor_id, vendedor_nome)
    else:
        form = RelatorioComissaoVendasForm()
    
    return render(request, 'relatorios/criar_relatorio.html', {'form': form})

def get_porcentagem_comissao(margem_venda_item_pedido, comissao_lines):
    for line in comissao_lines:
        margem_inicial = line[0]
        margem_final = line[1]
        porcentagem_comissao = line[2]

        if margem_venda_item_pedido >= margem_inicial and margem_venda_item_pedido <= margem_final:
            return porcentagem_comissao
    raise Exception('Porcentagem de comissão não encontrada')

def get_partner_cnpj(partner_id):
    models, uid, db, password = authenticate_odoo()

    partner = models.execute_kw(db, uid, password, 'res.partner', 'search_read',
                                            [[
                                                ('id', '=', partner_id)
                                            ]], {'fields': ['l10n_br_cnpj']})

    cnpj = partner[0]['l10n_br_cnpj']
    return cnpj

def get_product_name(product_id):
    models, uid, db, password = authenticate_odoo()

    product = models.execute_kw(db, uid, password, 'product.product', 'search_read',
                                            [[
                                                ('id', '=', product_id)
                                            ]], {'fields': ['default_code']})

    return product[0]['default_code']

def authenticate_odoo():
    url = 'https://serp.indufix.com.br'
    db = 'odoo'
    username = 'ti@indufix.com.br'
    password = 'indufix-123'

    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

    return models, uid, db, password

def gerar_relatorio(request, data_inicial, data_final, vendedor_id, vendedor_nome):
    try:
        # Consultar dados com base no relatório
        with connections['doran'].cursor() as cursor:
            query = """
                    SELECT
                    TB_NOTA_SAIDA.NUMERO_NF,
                    CONVERT (DATE, DATA_EMISSAO_NF) AS DATA_EMISSAO_NF,
                    TB_NOTA_SAIDA.CODIGO_CLIENTE_NF,
                    SUM (CONVERT (FLOAT, TB_NOTA_SAIDA.TOTAL_PRODUTOS_NF)) AS TOTAL_PRODUTOS_NF
                    FROM TB_NOTA_SAIDA(NOLOCK)
                    JOIN TB_CFOP (NOLOCK) ON TB_CFOP.CODIGO_CFOP = TB_NOTA_SAIDA.CODIGO_CFOP_NF
                    JOIN TB_EMITENTE (NOLOCK) ON TB_EMITENTE.CODIGO_EMITENTE = TB_NOTA_SAIDA.CODIGO_EMITENTE_NF
                    WHERE TB_CFOP.OPERACAO_VENDA = 1
                    AND TB_NOTA_SAIDA.STATUS_NF = 4
                    AND TB_NOTA_SAIDA.CANCELADA_NF = 0
                    AND TB_NOTA_SAIDA.CODIGO_VENDEDOR_NF = %s
                    AND CONVERT (DATE, TB_NOTA_SAIDA.DATA_EMISSAO_NF) >= %s AND CONVERT (DATE, TB_NOTA_SAIDA.DATA_EMISSAO_NF) <= %s
                    AND TB_NOTA_SAIDA.CODIGO_EMITENTE_NF IN (1, 3)
                    GROUP BY TB_NOTA_SAIDA.NUMERO_NF,
                    CONVERT (DATE, DATA_EMISSAO_NF),
                    TB_NOTA_SAIDA.CODIGO_CLIENTE_NF
                    ORDER BY CONVERT (DATE, DATA_EMISSAO_NF), TB_NOTA_SAIDA.NUMERO_NF ASC
                    """

            cursor.execute(query, [int(vendedor_id), data_inicial, data_final])
            nfs = cursor.fetchall()

            query = """
                    SELECT
                    TB_NOTA_SAIDA.CODIGO_VENDEDOR_NF,
                    RTRIM (TB_NOTA_SAIDA.NOME_VENDEDOR_NF) AS NOME_VENDEDOR_NF,
                    TB_NOTA_SAIDA.NUMERO_NF,
                    CONVERT (DATE, TB_NOTA_SAIDA.DATA_EMISSAO_NF) AS DATA_EMISSAO_NF,
                    RTRIM (TB_NOTA_SAIDA.CODIGO_CFOP_NF) AS CODIGO_CFOP_NF,
                    RTRIM (TB_NOTA_SAIDA.NOME_FANTASIA_CLIENTE_NF) AS NOME_FANTASIA_CLIENTE_NF,
                    RTRIM (TB_ITEM_NOTA_SAIDA.CODIGO_PRODUTO_ITEM_NF) AS CODIGO_PRODUTO_ITEM_NF,
                    TB_NOTA_SAIDA.VALOR_FRETE_NF,
                    CONVERT (FLOAT, TB_ITEM_NOTA_SAIDA.QTDE_ITEM_NF * TB_PEDIDO_VENDA.CUSTO_TOTAL_ITEM_PEDIDO) AS CUSTO_ITEM,
                    CONVERT (FLOAT, TB_ITEM_NOTA_SAIDA.VALOR_TOTAL_ITEM_NF) AS VALOR_TOTAL_ITEM_NF,
                    CONVERT (FLOAT, TB_PEDIDO_VENDA.MARGEM_VENDA_ITEM_PEDIDO) AS MARGEM_VENDA_ITEM_PEDIDO,
                    TB_ITEM_NOTA_SAIDA.SEQUENCIA_ITEM_NF,
                    RTRIM (TB_NOTA_SAIDA.CNPJ_CLIENTE_NF) AS CNPJ_CLIENTE_NF,
                    RTRIM (TB_EMITENTE.NOME_FANTASIA_EMITENTE) AS NOME_FANTASIA_EMITENTE,
                    TB_NOTA_SAIDA.CODIGO_CLIENTE_NF
                    FROM TB_ITEM_NOTA_SAIDA(NOLOCK)
                    JOIN TB_NOTA_SAIDA (NOLOCK) ON TB_NOTA_SAIDA.NUMERO_SEQ = TB_ITEM_NOTA_SAIDA.NUMERO_ITEM_NF
                    JOIN TB_CFOP (NOLOCK) ON TB_CFOP.CODIGO_CFOP = TB_NOTA_SAIDA.CODIGO_CFOP_NF
                    JOIN TB_PEDIDO_VENDA (NOLOCK) ON TB_PEDIDO_VENDA.NUMERO_PEDIDO = TB_ITEM_NOTA_SAIDA.NUMERO_PEDIDO_VENDA AND TB_PEDIDO_VENDA.NUMERO_ITEM = TB_ITEM_NOTA_SAIDA.NUMERO_ITEM_PEDIDO_VENDA
                    JOIN TB_EMITENTE (NOLOCK) ON TB_EMITENTE.CODIGO_EMITENTE = TB_NOTA_SAIDA.CODIGO_EMITENTE_NF
                    WHERE TB_CFOP.OPERACAO_VENDA = 1
                    AND TB_NOTA_SAIDA.STATUS_NF = 4
                    AND TB_NOTA_SAIDA.CANCELADA_NF = 0
                    AND TB_NOTA_SAIDA.CODIGO_VENDEDOR_NF = %s
                    AND CONVERT (DATE, TB_NOTA_SAIDA.DATA_EMISSAO_NF) >= %s AND CONVERT (DATE, TB_NOTA_SAIDA.DATA_EMISSAO_NF) <= %s
                    AND CODIGO_EMITENTE_NF IN (1, 3)
                    GROUP BY TB_NOTA_SAIDA.NUMERO_NF,
                    TB_NOTA_SAIDA.CODIGO_VENDEDOR_NF,
                    TB_NOTA_SAIDA.NOME_VENDEDOR_NF,
                    TB_NOTA_SAIDA.DATA_EMISSAO_NF,
                    TB_NOTA_SAIDA.CODIGO_CFOP_NF,
                    TB_NOTA_SAIDA.NOME_FANTASIA_CLIENTE_NF,
                    TB_ITEM_NOTA_SAIDA.CODIGO_PRODUTO_ITEM_NF,
                    TB_NOTA_SAIDA.VALOR_FRETE_NF,
                    TB_ITEM_NOTA_SAIDA.QTDE_ITEM_NF,
                    TB_ITEM_NOTA_SAIDA.VALOR_CUSTO_ITEM_NF,
                    TB_ITEM_NOTA_SAIDA.VALOR_TOTAL_ITEM_NF,
                    TB_PEDIDO_VENDA.MARGEM_VENDA_ITEM_PEDIDO,
                    TB_ITEM_NOTA_SAIDA.SEQUENCIA_ITEM_NF,
                    RTRIM (TB_NOTA_SAIDA.CNPJ_CLIENTE_NF),
                    RTRIM (TB_EMITENTE.NOME_FANTASIA_EMITENTE),
                    TB_NOTA_SAIDA.CODIGO_CLIENTE_NF,
                    TB_PEDIDO_VENDA.CUSTO_TOTAL_ITEM_PEDIDO
                    ORDER BY CONVERT (DATE, TB_NOTA_SAIDA.DATA_EMISSAO_NF), NUMERO_NF ASC
                    """

            cursor.execute(query, [int(vendedor_id), data_inicial, data_final])
            items = cursor.fetchall()

            query = """
                    SELECT 
                    CONVERT (FLOAT, MARGEM_INICIAL) AS MARGEM_INICIAL,
                    CONVERT (FLOAT, MARGEM_FINAL) AS MARGEM_FINAL,
                    CONVERT (FLOAT, PERCENTUAL_COMISSAO) AS PERCENTUAL_COMISSAO
                    FROM TB_TABELA_COMISSAO (NOLOCK)
                    WHERE TB_TABELA_COMISSAO.ID_VENDEDOR = %s
                    ORDER BY CONVERT (FLOAT, MARGEM_INICIAL) ASC
                    """

            cursor.execute(query, [int(vendedor_id)])
            comissao_lines = cursor.fetchall()

            query = """
                    SELECT 
                    CONVERT (FLOAT, VALOR_META_MENSAL) AS VALOR_META_MENSAL,
                    RTRIM (TB_VENDEDORES.EMAIL_VENDEDOR) AS EMAIL_VENDEDOR
                    FROM TB_VENDEDORES (NOLOCK)
                    WHERE ID_VENDEDOR = %s
                    """

            cursor.execute(query, [int(vendedor_id)])
            vendedor = cursor.fetchall()

            # Odoo
            models, uid, db, password = authenticate_odoo()

            email_vendedor = vendedor[0][1]
            tipo_pedidos = ['venda', 'venda-conta-ordem', 'venda_futura']
            invoices = models.execute_kw(db, uid, password, 'account.move', 'search_read',
                                                    [[
                                                        ('l10n_br_tipo_pedido', 'in', tipo_pedidos),
                                                        ('invoice_date', '>=', str(data_inicial)),
                                                        ('invoice_date', '<=', str(data_final)),
                                                        ('invoice_user_id.login', '=', email_vendedor),
                                                        ('picking_ids', '!=', False)
                                                    ]], {'fields': ['invoice_line_ids', 'invoice_user_id', 'l10n_br_numero_nf', 'invoice_date', 'partner_id', 'l10n_br_frete', 'empresa_faturamento_id']})

            if invoices:
                for invoice in invoices:
                    invoice_line_ids = invoice['invoice_line_ids']

                    lines = models.execute_kw(db, uid, password, 'account.move.line', 'search_read',
                                                        [[
                                                            ('id', 'in', invoice_line_ids)
                                                        ]], {'fields': ['product_id', 'quantity', 'l10n_br_cfop_codigo', 'l10n_br_total_nfe', 'sale_line_id']})

                    for line in lines:
                        sale_line_id = line['sale_line_id'][0]

                        sale_order_line = models.execute_kw(db, uid, password, 'sale.order.line', 'search_read',
                                                            [[
                                                                ('id', '=', sale_line_id)
                                                            ]], {'fields': ['custo_final_vendedor', 'price_unit', 'margem_vendedor']})

                        codigo_vendedor_nf = invoice['invoice_user_id'][0]
                        nome_vendedor_nf = invoice['invoice_user_id'][1]
                        numero_nf = invoice['l10n_br_numero_nf']
                        data_emissao_nf = datetime.datetime.strptime(invoice['invoice_date'], '%Y-%m-%d').date()
                        cfop = line['l10n_br_cfop_codigo']
                        nome_cliente = invoice['partner_id'][1]
                        codigo_produto_item = get_product_name(line['product_id'][0])
                        valor_frete_nf = invoice['l10n_br_frete']
                        custo_total = line['quantity'] * sale_order_line[0]['custo_final_vendedor']
                        total_item = line['quantity'] * sale_order_line[0]['price_unit']
                        margem_vendedor = sale_order_line[0]['margem_vendedor']
                        sequencia_item_nf = invoice['id']
                        cnpj_cliente_nf = get_partner_cnpj(invoice['partner_id'][0])
                        nome_fantasia_emitente = invoice['empresa_faturamento_id'][1]
                        items.append([
                            codigo_vendedor_nf, nome_vendedor_nf, numero_nf, data_emissao_nf, cfop, nome_cliente, codigo_produto_item, valor_frete_nf, 
                            custo_total, total_item, margem_vendedor, sequencia_item_nf, cnpj_cliente_nf, nome_fantasia_emitente
                        ])

        valor_total_nf = 0
        for nf in nfs:
            codigo_cliente_nf = int(nf[2])
            if codigo_cliente_nf == 52916:  # KATRIUM
                valor_total_nf += (nf[3] * 0.30)
            else:
                valor_total_nf += nf[3]

        valor_meta_mensal = vendedor[0][0]
        porcentagem_atingida = valor_total_nf / valor_meta_mensal
        if porcentagem_atingida < 0.50:
            fator_ajuste = 0.70
        elif porcentagem_atingida >= 0.50 and porcentagem_atingida < 0.80:
            fator_ajuste = 0.80
        elif porcentagem_atingida >= 0.80 and porcentagem_atingida < 1.20:
            fator_ajuste = 1.00
        elif porcentagem_atingida >= 1.20:
            fator_ajuste = 1.20

        values = []
        total_valor_total_item_nf = 0
        total_valor_comissao = 0

        items.sort(key=lambda x: (x[3], x[2]))
        for item in items:
            value = {}

            value['numero_nf'] = int(item[2])
            value['data_emissao_nf'] = item[3].strftime('%d/%m/%Y')
            value['emitente'] = item[13]
            value['nome_fantasia_cliente'] = item[5]
            value['codigo_produto_item'] = item[6]
            value['custo_total_item_nf'] = locale.currency(item[8], grouping=True)

            codigo_cliente_nf = int(item[14]) if len(item) > 14 and item[14] else 0
            if codigo_cliente_nf == 52916:  # KATRIUM
                valor_total_item_nf = item[9] * 0.30
            else:
                valor_total_item_nf = item[9]

            margem_venda_item_pedido = item[10]
            porcentagem_comissao = get_porcentagem_comissao(margem_venda_item_pedido, comissao_lines)
            porcentagem_comissao = round(porcentagem_comissao * fator_ajuste, 2)
            valor_comissao = valor_total_item_nf * (porcentagem_comissao / 100)

            value['valor_total_item_nf'] = locale.currency(valor_total_item_nf, grouping=True)
            value['margem_venda_item_pedido'] = margem_venda_item_pedido
            value['porcentagem_comissao'] = porcentagem_comissao
            value['valor_comissao'] = locale.currency(valor_comissao, grouping=True)
            total_valor_total_item_nf += valor_total_item_nf
            total_valor_comissao += valor_comissao
            values.append(value)

        return render(request, 'relatorios/relatorio_template.html', {
            'values': values,
            'vendedor': vendedor_nome,
            'data_inicial': data_inicial,
            'data_final': data_final,
            'total_valor_total_item_nf': locale.currency(total_valor_total_item_nf, grouping=True),
            'total_valor_comissao': locale.currency(total_valor_comissao, grouping=True)
        })
    except Exception as e:
        print(e)

def bx24_callmethod(method, endpoint, data=None):
    url = f"https://indufix.bitrix24.com.br/rest/92987/gi156k563ok7bfm8/{endpoint}"

    payload = json.dumps(data)

    headers = {
        'Content-Type': 'application/json',
        'Cookie': 'BITRIX_SM_SALE_UID=0; qmb=0.'
    }

    response = requests.request(method, url, headers=headers, data=payload)
    return response

@api_view(['POST'])
def post_bitrix(request):
    data_atual = datetime.datetime.today().date()
    logger.info(str(data_atual) + ' - ' + str(request.data))

    id_deal_bx24 = int(request.data['data[FIELDS][ID]'])
    deal_bx24_data = bx24_callmethod("GET", f"crm.deal.get?id={int(id_deal_bx24)}")
    stage_bx24 = deal_bx24_data['result']['STAGE_ID']
    orcamento_doran_bx24 = deal_bx24_data['result']['UF_CRM_5CB5D947C451E']
    list_stage_lose = ['LOSE', '7', '33', '8', '31', '32', '9', 'ON_HOLD', '10', '25', '26', '17', '29', '34']

    if str(stage_bx24) in list_stage_lose:
        if orcamento_doran_bx24:
            orcamento = Orcamentos()

            orcamento_doran_bx24 = int(orcamento_doran_bx24)
            orcamento.create_crm_doran(orcamento_doran_bx24)
            novo_numero_orcamento = orcamento.create_orcamento_doran(orcamento_doran_bx24)
            file_base64 = orcamento.create_pdf(orcamento_doran_bx24)

            data = {
                "id": int(id_deal_bx24),
                "fields": {
                    "UF_CRM_1669204231": str(novo_numero_orcamento),
                    "UF_CRM_5E4E8EC995042": {
                        "fileData": [
                            "orcamento.pdf",
                            str(file_base64)
                        ]
                    }

                }
            }
            response = bx24_callmethod("POST", "crm.deal.update", data)
            print(response)

    return Response('API Executada com sucesso!')

@api_view(['GET', 'POST'])
def orcamento_html(request, pk):
    id_deal_bx24 = pk
    deal_bx24_data = bx24_callmethod("GET", f"crm.deal.get?id={int(id_deal_bx24)}")
    deal_bx24_data = deal_bx24_data.json().get("result")
    orcamento_doran_bx24 = deal_bx24_data['UF_CRM_5CB5D947C451E']

    if orcamento_doran_bx24:
        orcamento = Orcamentos()

        html = orcamento.html_orcamento_pdf(orcamento_doran_bx24)

        data = {
            "id": int(id_deal_bx24),
            "fields": {
                "UF_CRM_1679061326": str(html)
            }
        }
        response = bx24_callmethod("POST", "crm.deal.update", data)
        print(response)

    return Response('API Executada com sucesso!')

@api_view(['POST'])
def api_campanha(request):
    try:
        data_atual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(str(data_atual) + ' - ' + str(request.data))

        id_bitrix = request.data["ID"]
        numero_orcamento = int(request.data["NrOrcamento"])
        inscricao_estadual = request.data["InscricaoEstadual"]

        if inscricao_estadual is None or inscricao_estadual == "":
            inscricao_estadual = ""

        # situacao = request.data["SituacaoCnpj"]
        # if situacao != '' and situacao is not None:
        #     if situacao.upper() == 'ATIVA' or situacao.upper() == 'ATIVO' or situacao.upper() == 'HABILITADA' or situacao.upper() == 'HABILITADO' or situacao.upper() == 'HABILITADO - ATIVO' or situacao.upper() == 'ATIVO - HABILITADO':
        #         cliente_contribuinte_icms = 1
        #     else:
        #         cliente_contribuinte_icms = 2
        # else:
        #     cliente_contribuinte_icms = 2

        cliente_contribuinte_icms = 1
        orcamento = Orcamentos()
        orcamento_negociado = orcamento.negocia_orcamento_doran(numero_orcamento, cliente_contribuinte_icms)

        with connections['doran'].cursor() as cursor:
            query = """SELECT 
                       TOP 1
                       NUMERO_ITEM_ORCAMENTO
                       FROM TB_CUSTO_ITEM_ORCAMENTO_VENDA (NOLOCK)
                       WHERE NUMERO_ORCAMENTO = %s AND OBS_CUSTO_VENDA LIKE %s"""

            cursor.execute(query, [numero_orcamento, '%UP_BX24%'])
            itens_negociados = cursor.fetchall()

        if orcamento_negociado and itens_negociados:
            orcamento.data_minima_fornecimento(numero_orcamento)
            file_base64, file_name = orcamento.create_pdf(numero_orcamento, inscricao_estadual)

            data = {
                "id": int(id_bitrix),
                "fields": {
                    "UF_CRM_1670534553362": {
                        "fileData": [
                            file_name,
                            str(file_base64)
                        ]
                    }

                }
            }
            response = bx24_callmethod("POST", "crm.deal.update", data)
            print(response)

            # data = {"dialog_id": 8, "message": f"Negociação Especial => Executada com Sucesso! [Nº ORÇAMENTO: {numero_orcamento}]"}
            # bx24_callmethod("POST", "im.message.add", data)

            data = {"dialog_id": 37985, "message": f"Negociação Especial => Executada com Sucesso! [Nº ORÇAMENTO: {numero_orcamento}]"}
            bx24_callmethod("POST", "im.message.add", data)

            # orcamento.create_crm_doran(numero_orcamento)
            # orcamento.create_orcamento_doran(numero_orcamento)

        return Response('API Executada!')

    except Exception as e:
        data = {"dialog_id": 8, "message": "Negociação Especial: Error => " + str(e) + f"[Nº ORÇAMENTO: {numero_orcamento}]"}
        bx24_callmethod("POST", "im.message.add", data)

        data = {"dialog_id": 37985, "message": "Negociação Especial: Error => " + str(e) + f"[Nº ORÇAMENTO: {numero_orcamento}]"}
        bx24_callmethod("POST", "im.message.add", data)

@api_view(['POST'])
def api_campanha_lead(request):
    try:
        data_atual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(str(data_atual) + ' - ' + str(request.data))

        id_bitrix = request.data["ID"]
        numero_orcamento = int(request.data["NrOrcamento"])
        inscricao_estadual = request.data["InscricaoEstadual"]

        if inscricao_estadual is None or inscricao_estadual == "":
            inscricao_estadual = ""

        # situacao = request.data["SituacaoCnpj"]
        # if situacao != '' and situacao is not None:
        #     if situacao.upper() == 'ATIVA' or situacao.upper() == 'ATIVO' or situacao.upper() == 'HABILITADA' or situacao.upper() == 'HABILITADO' or situacao.upper() == 'HABILITADO - ATIVO' or situacao.upper() == 'ATIVO - HABILITADO':
        #         cliente_contribuinte_icms = 1
        #     else:
        #         cliente_contribuinte_icms = 2
        # else:
        #     cliente_contribuinte_icms = 2

        cliente_contribuinte_icms = 1
        orcamento = Orcamentos()
        orcamento_negociado = orcamento.negocia_orcamento_doran(numero_orcamento, cliente_contribuinte_icms)

        with connections['doran'].cursor() as cursor:
            query = """SELECT 
                       TOP 1
                       NUMERO_ITEM_ORCAMENTO
                       FROM TB_CUSTO_ITEM_ORCAMENTO_VENDA (NOLOCK)
                       WHERE NUMERO_ORCAMENTO = %s AND OBS_CUSTO_VENDA LIKE %s"""

            cursor.execute(query, [numero_orcamento, '%UP_BX24%'])
            itens_negociados = cursor.fetchall()

        if orcamento_negociado and itens_negociados:
            orcamento.data_minima_fornecimento(numero_orcamento)
            file_base64, file_name = orcamento.create_pdf(numero_orcamento, inscricao_estadual)

            data = {
                "id": int(id_bitrix),
                "fields": {
                    "UF_CRM_1671212861": {
                        "fileData": [
                            file_name,
                            str(file_base64)
                        ]
                    }

                }
            }
            response = bx24_callmethod("POST", "crm.company.update", data)
            print(response)

            # data = {"dialog_id": 8, "message": f"Negociação Especial => Executada com Sucesso! [Nº ORÇAMENTO: {numero_orcamento}]"}
            # bx24_callmethod("POST", "im.message.add", data)

            data = {"dialog_id": 37985, "message": f"Negociação Especial => Executada com Sucesso! [Nº ORÇAMENTO: {numero_orcamento}]"}
            bx24_callmethod("POST", "im.message.add", data)

            # orcamento.create_crm_doran(numero_orcamento)
            # orcamento.create_orcamento_doran(numero_orcamento)

        return Response('API Executada!')

    except Exception as e:
        data = {"dialog_id": 8, "message": "Negociação Especial: Error => " + str(e) + f"[Nº ORÇAMENTO: {numero_orcamento}]"}
        bx24_callmethod("POST", "im.message.add", data)

        data = {"dialog_id": 37985, "message": "Negociação Especial: Error => " + str(e) + f"[Nº ORÇAMENTO: {numero_orcamento}]"}
        bx24_callmethod("POST", "im.message.add", data)

# def api_campanha2():
#     try:
#         numero_orcamento = 347495
#         cliente_contribuinte_icms = 1
#         inscricao_estadual = ""
#         orcamento = Orcamentos()
#         orcamento_negociado = orcamento.negocia_orcamento_doran(numero_orcamento, cliente_contribuinte_icms)
#
#         with connections['doran'].cursor() as cursor:
#             query = """SELECT
#                        TOP 1
#                        NUMERO_ITEM
#                        FROM TB_ITEM_ORCAMENTO_VENDA (NOLOCK)
#                        WHERE NUMERO_ORCAMENTO = %s AND PRECO_PRODUTO > 0"""
#
#             cursor.execute(query, [numero_orcamento])
#             itens_negociados = cursor.fetchall()
#
#         if orcamento_negociado and itens_negociados:
#             orcamento.data_minima_fornecimento(numero_orcamento)
#             file_base64, file_name = orcamento.create_pdf(numero_orcamento, inscricao_estadual)
#
#             data = {
#                 "id": 185521,
#                 "fields": {
#                     "UF_CRM_1670534553362": {
#                         "fileData": [
#                             file_name,
#                             str(file_base64)
#                         ]
#                     }
#
#                 }
#             }
#             response = bx24_callmethod("POST", "crm.deal.update", data)
#             print(response)
#
#             data = {"dialog_id": 8, "message": f"Negociação Especial => Executada com Sucesso! [Nº ORÇAMENTO: {numero_orcamento}]"}
#             bx24_callmethod("POST", "im.message.add", data)
#
#             data = {"dialog_id": 37985, "message": f"Negociação Especial => Executada com Sucesso! [Nº ORÇAMENTO: {numero_orcamento}]"}
#             bx24_callmethod("POST", "im.message.add", data)
#             # orcamento.create_crm_doran(numero_orcamento)
#             # orcamento.create_orcamento_doran(numero_orcamento)
#
#         return Response('Teste OK!')
#
#     except Exception as e:
#         data = {"dialog_id": 8, "message": "Negociação Especial: Error => " + str(e) + f"[Nº ORÇAMENTO: {numero_orcamento}]"}
#         bx24_callmethod("POST", "im.message.add", data)
#
#         data = {"dialog_id": 37985, "message": "Negociação Especial: Error => " + str(e) + f"[Nº ORÇAMENTO: {numero_orcamento}]"}
#         bx24_callmethod("POST", "im.message.add", data)

@api_view(['POST'])
def api_troca_vendedor_doran(request):
    try:
        data_atual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(str(data_atual) + ' - ' + str(request.data))

        cnpj_bx24 = request.data["cnpj"]
        responsavel_bx24 = request.data["vendedor"]

        if not cnpj_bx24 or not responsavel_bx24:
            return Response('CNPJ ou vendedor não informado', status=400)

        models, uid, db, password = authenticate_odoo()
            
        partner_id = models.execute_kw(db, uid, password, 'res.partner', 'search', [[('l10n_br_cnpj', '=', cnpj_bx24)]])
        if not partner_id:
            return Response('Parceiro não encontrado ODOO', status=404)

        partner_data = models.execute_kw(db, uid, password, 'res.partner', 'read', [[partner_id[0]]], {'fields': ['user_id']})
        if partner_data and partner_data[0]['user_id']:
            nome_vendedor_antigo = partner_data[0]['user_id'][1]
        else:
            nome_vendedor_antigo = 'Não definido'
        
        user_id = models.execute_kw(db, uid, password, 'res.users', 'search', [[('name', '=', responsavel_bx24)]])
        if not user_id:
            return Response('Vendedor não encontrado ODOO', status=404)
        
        models.execute_kw(db, uid, password, 'res.partner', 'write', [[partner_id[0]], {'user_id': user_id[0]}])

        return Response('Alterado o vendedor de ' + str(nome_vendedor_antigo) + ' para ' + str(responsavel_bx24))
                
    except Exception as e:
        data = {"dialog_id": 8, "message": str(e)}
        bx24_callmethod("POST", "im.message.add", data)

@api_view(['GET'])
def consulta_orcamento(request, pk):
    try:
        numero_orcamento = int(pk)
        with connections['doran'].cursor() as cursor:
            query = """
                    SELECT 
                    RTRIM (TB_CRM.CNPJ_CLIENTE) AS CNPJ_CLIENTE,
                    CONVERT (FLOAT, SUM (TB_ITEM_ORCAMENTO_VENDA.VALOR_TOTAL + TB_ITEM_ORCAMENTO_VENDA.VALOR_IPI + TB_ITEM_ORCAMENTO_VENDA.VALOR_ICMS_SUBS)) AS TOTAL_ORCAMENTO
                    FROM TB_ORCAMENTO_VENDA (NOLOCK)
                    JOIN TB_ITEM_ORCAMENTO_VENDA (NOLOCK) ON TB_ITEM_ORCAMENTO_VENDA.NUMERO_ORCAMENTO = TB_ORCAMENTO_VENDA.NUMERO_ORCAMENTO
                    JOIN TB_CRM (NOLOCK) ON TB_CRM.NUMERO_CRM = TB_ORCAMENTO_VENDA.NUMERO_CRM
                    WHERE TB_ORCAMENTO_VENDA.NUMERO_ORCAMENTO = %s
                    GROUP BY RTRIM (TB_CRM.CNPJ_CLIENTE)
                    """

            cursor.execute(query, [numero_orcamento])
            dados_orcamento = cursor.fetchall()

            for dados in dados_orcamento:
                cnpj_orcamento = dados[0]
                valor_total_orcamento = round(float(dados[1]), 2)

            string_response = {'cnpj': cnpj_orcamento,
                               'valor_total': valor_total_orcamento}

            return Response(string_response)

    except Exception as e:
        data = {"dialog_id": 8, "message": 'Erro Consulta Orçamento: ' + str(e)}
        bx24_callmethod("POST", "im.message.add", data)

@csrf_exempt
def lista_locais(request):
    try:
        with connections['doran'].cursor() as cursor:
            cursor.execute("""
                SELECT RTRIM(DESCRICAO_LOCAL) 
                FROM TB_LOCAL (NOLOCK) 
                ORDER BY DESCRICAO_LOCAL ASC
            """)
            rows = cursor.fetchall()
            locais = [row[0] for row in rows]
            return JsonResponse(locais, safe=False)
    except Exception as e:
        return JsonResponse({'erro': str(e)}, status=500)


@csrf_exempt
def buscar_local(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            local_id = data.get('local_id')

            with connections['doran'].cursor() as cursor:
                cursor.execute("""
                    SELECT RTRIM (DESCRICAO_LOCAL) AS DESCRICAO_LOCAL
                    FROM TB_LOCAL 
                    WHERE ID_LOCAL = %s
                """, [local_id])
                local = cursor.fetchone()

                if local:
                    return JsonResponse({
                        'success': True,
                        'descricao': local[0]
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'error': 'Local não encontrado'
                    }, status=404)

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

    return JsonResponse({
        'error': 'Método não permitido'
    }, status=405)

@csrf_exempt
def buscar_dados_item_oc(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            numero_pedido = data.get('numero_pedido')
            numero_item = data.get('numero_item')

            with connections['default'].cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        QTDE_NFE,
                        NUMERO_NFE
                    FROM TB_ITEM_NOTA_ENTRADA_OC
                    WHERE NUMERO_PEDIDO_COMPRA = %s AND NUMERO_ITEM_COMPRA = %s
                    LIMIT 1
                """, [int(numero_pedido), str(numero_item)])

                row = cursor.fetchone()

                if row:
                    return JsonResponse({
                        'success': True,
                        'qtde_recebida': float(row[0]),
                        'numero_nf': int(row[1])
                    })
                else:
                    return JsonResponse({'success': False, 'message': 'Dados não encontrados'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
def salvar_rnc(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            numero_pedido = data.get('numero_pedido')
            numero_item = data.get('numero_item')
            descricao = data.get('descricao')
            usuario = data.get('usuario')

            with connections['doran'].cursor() as cursor:
                # ID Usuário
                cursor.execute("""
                    SELECT 
                    ID_USUARIO,
                    RTRIM (NOME_USUARIO) AS NOME_USUARIO
                    FROM TB_USUARIOS (NOLOCK)
                    WHERE LOGIN_USUARIO = %s
                """, [usuario.upper()])
                user = cursor.fetchone()

                if user:
                    id_usuario = int(user[0])
                    nome_usuario = user[1]

                cursor.execute("""
                    SELECT 
                    RTRIM (CODIGO_PRODUTO_COMPRA) AS CODIGO_PRODUTO_COMPRA,
                    CONVERT (DATE, PREVISAO_ENTREGA_ITEM_COMPRA) AS PREVISAO_ENTREGA_ITEM_COMPRA,
                    TB_PEDIDO_VENDA.NUMERO_PEDIDO,
                    TB_PEDIDO_VENDA.NUMERO_ITEM,
                    CONVERT (DATE, ENTREGA_PEDIDO) AS ENTREGA_PEDIDO,
                    RTRIM (TB_PEDIDO_VENDA.STATUS_ITEM_PEDIDO) AS STATUS_ITEM_PEDIDO
                    FROM TB_PEDIDO_COMPRA (NOLOCK)
                    LEFT JOIN TB_ASSOCIACAO_COMPRA_VENDA (NOLOCK) ON TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_PEDIDO_COMPRA = TB_PEDIDO_COMPRA.NUMERO_PEDIDO_COMPRA
                    AND TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_ITEM_COMPRA = TB_PEDIDO_COMPRA.NUMERO_ITEM_COMPRA
                    LEFT JOIN TB_PEDIDO_VENDA (NOLOCK) ON TB_PEDIDO_VENDA.NUMERO_PEDIDO = TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_PEDIDO_VENDA
                    AND TB_PEDIDO_VENDA.NUMERO_ITEM = TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_ITEM_VENDA
                    WHERE TB_PEDIDO_COMPRA.NUMERO_PEDIDO_COMPRA = %s AND TB_PEDIDO_COMPRA.NUMERO_ITEM_COMPRA = %s
                """, [numero_pedido, numero_item])
                items = cursor.fetchall()

                message = "[b]Item marcado com RNC[/b] \n\n"
                for item in items:
                    codigo_produto_compra = item[0]
                    entrega_compra = item[1].strftime("%d/%m/%Y")
                    numero_pedido_venda = int(item[2]) if item[2] else 0
                    numero_item_venda = int(item[3]) if item[3] else 0
                    entrega_venda = item[4].strftime("%d/%m/%Y") if item[4] else False
                    status_item_pedido = int(item[5]) if item[5] else False
                    message += (
                        f"- Nº Pedido de Compra: {numero_pedido} / "
                        f"Cód. Produto Compra: {codigo_produto_compra} / "
                        f"Entrega Compra: {entrega_compra} / "
                        f"Pedido Venda: {numero_pedido_venda} / "
                        f"Entrega Venda: {entrega_venda} / "
                        f"Não Conformidade: {descricao} / "
                        f"Responsável: {nome_usuario}"
                    )

                    if numero_pedido_venda > 0 and numero_item_venda > 0 and status_item_pedido:
                        if status_item_pedido not in (7, 8, 17):
                            cursor.execute("""
                                UPDATE TB_PEDIDO_VENDA SET 
                                STATUS_ITEM_PEDIDO = 27
                                WHERE NUMERO_PEDIDO = %s AND NUMERO_ITEM = %s
                            """, [numero_pedido_venda, numero_item_venda])

                            # Cria mudança de fases no pedido de venda
                            cursor.execute("""
                                SELECT 
                                TOP 1
                                ID_STATUS_NOVO,
                                DATA_MUDANCA,
                                ID_PRODUTO
                                FROM TB_MUDANCA_STATUS_PEDIDO (NOLOCK)
                                WHERE NUMERO_PEDIDO_VENDA = %s AND NUMERO_ITEM_VENDA = %s
                                ORDER BY ID_MUDANCA_FASE DESC
                            """, [numero_pedido_venda, numero_item_venda])
                            item = cursor.fetchone()

                            if item:
                                id_status_anterior = item[0]
                                data_status_anterior = item[1]
                                id_produto = int(item[2])

                                cursor.execute("""
                                    INSERT INTO 
                                    TB_MUDANCA_STATUS_PEDIDO
                                    (NUMERO_PEDIDO_VENDA, NUMERO_ITEM_VENDA, DATA_MUDANCA, ID_USUARIO, ID_STATUS_ANTERIOR, ID_STATUS_NOVO, DATA_STATUS_ANTERIOR, ID_PRODUTO)
                                    VALUES
                                    (%s, %s, GETDATE(), %s, %s, %s, %s, %s)
                                """, [numero_pedido_venda, numero_item_venda, id_usuario, id_status_anterior, 27, data_status_anterior, id_produto])

                cursor.execute("""
                    UPDATE TB_PEDIDO_COMPRA SET 
                    NAO_CONFORMIDADE = 1,
                    DESCRICAO_NAO_CONFORMIDADE = %s
                    WHERE NUMERO_PEDIDO_COMPRA = %s AND NUMERO_ITEM_COMPRA = %s
                """, [descricao, numero_pedido, numero_item])

            data = {
                "dialog_id": 127,
                "message": message
            }
            bx24_callmethod("POST", "im.message.add", data)

            data = {
                "dialog_id": 8,
                "message": message
            }
            bx24_callmethod("POST", "im.message.add", data)

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'error': 'Método não permitido'}, status=405)

def parse_quantity(value):
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    value = str(value).strip()

    # Verifica se já está no formato float (ponto decimal)
    if '.' in value and ',' not in value:
        try:
            return float(value)
        except ValueError:
            pass

    # Remove todos os pontos (separadores de milhar)
    value = value.replace('.', '')

    # Substitui vírgula por ponto (decimal)
    value = value.replace(',', '.')

    try:
        return float(value)
    except ValueError:
        return 0.0

@csrf_exempt
@transaction.atomic
def salvar_conferencia(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            mes_ano_atual = datetime.datetime.now().strftime("%m%Y")

            usuario = request.user.username
            item_id = data.get('item_id')
            qtde_oc = float(data.get('qtde_oc'))
            qtde_recebida = parse_quantity(data.get('qtde_recebida'))
            local = data.get('local')
            numero_nf = int(data.get('numero_nf'))
            numero_pedido = data.get('numero_pedido')
            codigo_produto_compra = data.get('codigo_produto_compra')

            with transaction.atomic(using='doran'):
                with connections['doran'].cursor() as cursor:
                    # Quantidade Total Recebida
                    cursor.execute("""
                        SELECT 
                        SUM (QTDE_RECEBIDA) AS QTDE_RECEBIDA
                        FROM TB_RECEBIMENTO_PEDIDO_COMPRA (NOLOCK)
                        WHERE NUMERO_PEDIDO_COMPRA = %s AND NUMERO_ITEM_COMPRA = %s
                    """, [numero_pedido, item_id])
                    result = cursor.fetchone()

                    if result and result[0] is not None:
                        total_qtde_recebida = float(result[0]) + qtde_recebida
                    else:
                        total_qtde_recebida = qtde_recebida

                    # ID Usuário
                    cursor.execute("""
                        SELECT 
                        ID_USUARIO
                        FROM TB_USUARIOS (NOLOCK)
                        WHERE LOGIN_USUARIO = %s
                    """, [usuario.upper()])
                    id_usuario = cursor.fetchone()

                    if id_usuario:
                        id_usuario = int(id_usuario[0])

                    # Atualiza Status e Local do item do pedido de compras
                    cursor.execute("""
                        SELECT 
                        ID_LOCAL
                        FROM TB_LOCAL (NOLOCK)
                        WHERE DESCRICAO_LOCAL = %s
                    """, [local])
                    id_local = cursor.fetchone()[0]

                    if total_qtde_recebida >= qtde_oc:
                        status_item = 4  # ENTREGUE TOTAL
                    else:
                        status_item = 3  # ENTREGUE PARCIAL

                    cursor.execute("""
                        UPDATE TB_PEDIDO_COMPRA SET
                        STATUS_ITEM_COMPRA = %s,
                        ID_LOCAL_PROVISORIO = %s
                        WHERE NUMERO_PEDIDO_COMPRA = %s AND NUMERO_ITEM_COMPRA = %s
                    """, [status_item, int(id_local), numero_pedido, item_id])

                    # Busca último número de lote utilizado
                    cursor.execute("""
                        SELECT TOP 1 NUMERO_LOTE 
                        FROM TB_RECEBIMENTO_PEDIDO_COMPRA (NOLOCK) 
                        ORDER BY NUMERO_RECEBIMENTO DESC
                    """)
                    ultimo_lote = cursor.fetchone()[0]
                    numero_lote = ultimo_lote + 1
                    numero_lote = str(numero_lote) + f"/{mes_ano_atual}"

                    # Calcula peso aproximado
                    cursor.execute("""
                        SELECT 
                        CONVERT (FLOAT, PESO_PRODUTO) AS PESO_PRODUTO
                        FROM TB_PRODUTO (NOLOCK)
                        WHERE CODIGO_PRODUTO = %s
                    """, [codigo_produto_compra])
                    peso_bruto = cursor.fetchone()[0]
                    peso_aproximado = float(peso_bruto) * float(qtde_recebida)

                    # Cria recebimento de mercadoria
                    cursor.execute("""
                        INSERT INTO 
                        TB_RECEBIMENTO_PEDIDO_COMPRA 
                        (DATA_RECEBIMENTO, NUMERO_PEDIDO_COMPRA, NUMERO_ITEM_COMPRA, NUMERO_NF, QTDE_RECEBIDA, PESO_RECEBIDO, NUMERO_LOTE_RECEBIMENTO, ID_LOCAL, NUMERO_LOTE)
                        VALUES
                        (GETDATE(), %s, %s, %s, %s, %s, %s, %s, %s)
                    """, [numero_pedido, item_id, numero_nf, qtde_recebida, peso_aproximado, numero_lote, int(id_local), ultimo_lote + 1])

                    # Cria rastro recebimento de mercadoria
                    data_hora = datetime.datetime.now()
                    historico = f'NUMERO_RECEBIMENTO: 0 / DATA_RECEBIMENTO: {data_hora} / NUMERO_PEDIDO_COMPRA: {numero_pedido} / NUMERO_ITEM_COMPRA: {item_id} / ' \
                                f'CODIGO_PRODUTO_COMPRA: {codigo_produto_compra} / NUMERO_NF: {numero_nf} / QTDE_ITEM_COMPRA: {qtde_oc} / QTDE_RECEBIDA: {qtde_recebida} / ' \
                                f'NUMERO_LOTE_RECEBIMENTO: {numero_lote} / ID_LOCAL: {id_local} / NUMERO_LOTE: {ultimo_lote + 1}'
                    cursor.execute("""
                        INSERT INTO 
                        TB_RASTRO 
                        (DATA_RASTRO, ID_USUARIO, TABELA_RASTRO, HISTORICO_RASTRO, TIPO_RASTRO, NUMERO_LOTE)
                        VALUES
                        (GETDATE(), %s, 'TB_RECEBIMENTO_PEDIDO_COMPRA', %s, 'I', %s)
                    """, [id_usuario, historico, numero_lote])

                    # Localiza os pedidos de venda associado e atualiza o status
                    cursor.execute("""
                        SELECT 
                        TB_PEDIDO_VENDA.NUMERO_PEDIDO,
                        TB_PEDIDO_VENDA.NUMERO_ITEM,
                        RTRIM (TB_PEDIDO_VENDA.CODIGO_PRODUTO_PEDIDO) AS CODIGO_PRODUTO_PEDIDO,
                        CONVERT (FLOAT, TB_PEDIDO_VENDA.QTDE_PRODUTO_ITEM_PEDIDO) AS QTDE_PRODUTO_ITEM_PEDIDO,
                        TB_PEDIDO_VENDA.STATUS_ITEM_PEDIDO,
                        TB_PEDIDO_VENDA.ID_PRODUTO_PEDIDO
                        FROM TB_ASSOCIACAO_COMPRA_VENDA (NOLOCK)
                        JOIN TB_PEDIDO_VENDA (NOLOCK) ON TB_PEDIDO_VENDA.NUMERO_PEDIDO = TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_PEDIDO_VENDA
                        AND TB_PEDIDO_VENDA.NUMERO_ITEM = TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_ITEM_VENDA
                        WHERE TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_PEDIDO_COMPRA = %s AND TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_ITEM_COMPRA = %s
                    """, [numero_pedido, item_id])
                    items = cursor.fetchall()

                    qtde_item_venda = 0
                    for item in items:
                        numero_pedido_venda = int(item[0])
                        numero_item_pedido_venda = int(item[1])
                        codigo_produto_venda = item[2]
                        qtde_item_venda += float(item[3])
                        status_item_pedido = int(item[4])
                        id_produto_venda = int(item[5])

                        if status_item_pedido not in (7, 8, 17, 27):
                            if codigo_produto_compra == codigo_produto_venda:
                                status_item_pedido = 23  # PRÉ-SEPARAÇÃO
                            else:
                                status_item_pedido = 12  # BENEFICIAMENTO

                        cursor.execute("""
                            UPDATE TB_PEDIDO_VENDA SET 
                            STATUS_ITEM_PEDIDO = %s,
                            NUMERO_LOTE_ITEM_PEDIDO = %s
                            WHERE NUMERO_PEDIDO = %s AND NUMERO_ITEM = %s
                        """, [status_item_pedido, numero_lote, numero_pedido_venda, numero_item_pedido_venda])

                        if status_item_pedido not in (7, 8, 17, 27):
                            # Cria mudança de fases no pedido de venda
                            cursor.execute("""
                                SELECT 
                                TOP 1
                                ID_STATUS_NOVO,
                                DATA_MUDANCA,
                                ID_PRODUTO
                                FROM TB_MUDANCA_STATUS_PEDIDO (NOLOCK)
                                WHERE NUMERO_PEDIDO_VENDA = %s AND NUMERO_ITEM_VENDA = %s
                                ORDER BY ID_MUDANCA_FASE DESC
                            """, [numero_pedido_venda, numero_item_pedido_venda])
                            item = cursor.fetchone()

                            if item:
                                id_status_anterior = item[0]
                                data_status_anterior = item[1]

                                cursor.execute("""
                                    INSERT INTO 
                                    TB_MUDANCA_STATUS_PEDIDO
                                    (NUMERO_PEDIDO_VENDA, NUMERO_ITEM_VENDA, DATA_MUDANCA, ID_USUARIO, ID_STATUS_ANTERIOR, ID_STATUS_NOVO, DATA_STATUS_ANTERIOR, ID_PRODUTO)
                                    VALUES
                                    (%s, %s, GETDATE(), %s, %s, %s, %s, %s)
                                """, [numero_pedido_venda, numero_item_pedido_venda, id_usuario, id_status_anterior, status_item_pedido, data_status_anterior, id_produto_venda])

                    # Cria movimentações de estoque
                    cursor.execute("""
                        SELECT 
                        NUMERO_RECEBIMENTO,
                        CONVERT (FLOAT, TB_PEDIDO_COMPRA.PRECO_ITEM_COMPRA) AS PRECO_ITEM_COMPRA,
                        TB_PEDIDO_COMPRA.CODIGO_FORNECEDOR,
                        TB_PEDIDO_COMPRA.ID_PRODUTO_COMPRA
                        FROM TB_RECEBIMENTO_PEDIDO_COMPRA (NOLOCK)
                        JOIN TB_PEDIDO_COMPRA (NOLOCK) ON TB_PEDIDO_COMPRA.NUMERO_PEDIDO_COMPRA = TB_RECEBIMENTO_PEDIDO_COMPRA.NUMERO_PEDIDO_COMPRA
                        AND TB_PEDIDO_COMPRA.NUMERO_ITEM_COMPRA = TB_RECEBIMENTO_PEDIDO_COMPRA.NUMERO_ITEM_COMPRA
                        WHERE TB_PEDIDO_COMPRA.NUMERO_PEDIDO_COMPRA = %s
                        AND TB_PEDIDO_COMPRA.NUMERO_ITEM_COMPRA = %s
                        AND NUMERO_LOTE_RECEBIMENTO = %s
                    """, [numero_pedido, item_id, numero_lote])
                    item = cursor.fetchone()

                    if item:
                        numero_recebimento = int(item[0])
                        preco_item_compra = float(item[1])
                        codigo_fornecedor = int(item[2])
                        id_produto_compra = int(item[3])

                        # ENTRADA POR RECEBIMENTO DE MERCADORIAS
                        cursor.execute("""
                            INSERT INTO TB_ESTOQUE (DATA_ESTOQUE, ID_PRODUTO, MOVTO_ESTOQUE, QTDE_ESTOQUE, NUMERO_SEQ_NF_SAIDA, NUMERO_SEQ_NF_ENTRADA, ID_LOCAL, CODIGO_MOVTO, NUMERO_LOTE, NUMERO_RECEBIMENTO, PRECO_CUSTO_PRODUTO, PRECO_VENDA_PRODUTO, SALDO_PRODUTO, OBS_FORNECEDOR, CODIGO_FORNECEDOR, ID_USUARIO_ETIQUETA, MARCA_IMPRESSAO_ETIQUETA)
                            VALUES (GETDATE(), %s, 0, %s, 0, 0, %s, 14, %s, %s, %s, 0, %s, '', %s, 0, 0)
                        """, [id_produto_compra, qtde_recebida, int(id_local), numero_lote, numero_recebimento, preco_item_compra, qtde_recebida, codigo_fornecedor])

                        if qtde_item_venda > 0:
                            # SAÍDA POR DÉBITO DE VENDAS
                            cursor.execute("""
                                INSERT INTO TB_ESTOQUE (DATA_ESTOQUE, ID_PRODUTO, MOVTO_ESTOQUE, QTDE_ESTOQUE, NUMERO_SEQ_NF_SAIDA, NUMERO_SEQ_NF_ENTRADA, ID_LOCAL, CODIGO_MOVTO, NUMERO_LOTE, NUMERO_RECEBIMENTO, PRECO_CUSTO_PRODUTO, PRECO_VENDA_PRODUTO, SALDO_PRODUTO, OBS_FORNECEDOR, ID_USUARIO_ETIQUETA, MARCA_IMPRESSAO_ETIQUETA, NUMERO_PEDIDO_COMPRA, NUMERO_ITEM_COMPRA)
                                VALUES (GETDATE(), %s, 0, %s, 0, 0, %s, 16, %s, %s, 0, 0, %s, '', 0, 0, %s, %s)
                            """, [id_produto_compra, -qtde_item_venda, int(id_local), numero_lote, numero_recebimento, -qtde_item_venda, numero_pedido, item_id])

            return JsonResponse({'success': True})

        except Exception as e:
            print('[Erro ao salvar conferência]', str(e))
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'error': 'Método não permitido'}, status=405)

@csrf_exempt
def salvar_fotos(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            pedido_id = data.get('pedido_id')
            item_id = data.get('item_id')
            fotos_base64 = data.get('fotos', [])

            def comprimir_imagem_base64(imagem_base64, tamanho=(800, 800), qualidade=60):
                if 'base64,' in imagem_base64:
                    imagem_base64 = imagem_base64.split('base64,')[1]
                imagem_decodificada = base64.b64decode(imagem_base64)
                imagem = Image.open(BytesIO(imagem_decodificada))

                imagem = imagem.convert("RGB")  # Garantir compatibilidade JPEG
                imagem.thumbnail(tamanho)

                buffer = BytesIO()
                imagem.save(buffer, format='JPEG', quality=qualidade)
                return buffer.getvalue()  # retorna bytes prontos para salvar

            with connections['doran'].cursor() as cursor:
                for foto_base64 in fotos_base64:
                    try:
                        imagem_comprimida = comprimir_imagem_base64(foto_base64)
                        cursor.execute("""
                            INSERT INTO TB_FOTO_RECEBIMENTO 
                            (NUMERO_PEDIDO_COMPRA, NUMERO_ITEM_COMPRA, DATA_FOTO, IMAGEM)
                            VALUES (%s, %s, GETDATE(), %s)
                        """, [pedido_id, item_id, imagem_comprimida])
                    except Exception as e:
                        print(f"Erro ao processar imagem: {str(e)}")
                        continue

                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM TB_FOTO_RECEBIMENTO 
                    WHERE NUMERO_PEDIDO_COMPRA = %s AND NUMERO_ITEM_COMPRA = %s
                """, [pedido_id, item_id])
                total_fotos = cursor.fetchone()[0]

                return JsonResponse({'success': True, 'total_fotos': total_fotos})

        except Exception as e:
            print(f"Erro ao salvar fotos: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'error': 'Método não permitido'}, status=405)

@csrf_exempt
def carregar_fotos(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            pedido_id = data.get('pedido_id')
            item_id = data.get('item_id')

            with connections['doran'].cursor() as cursor:
                cursor.execute("""
                    SELECT IMAGEM 
                    FROM TB_FOTO_RECEBIMENTO 
                    WHERE NUMERO_PEDIDO_COMPRA = %s AND NUMERO_ITEM_COMPRA = %s
                    ORDER BY DATA_FOTO DESC
                """, [pedido_id, item_id])
                fotos = cursor.fetchall()

                fotos_base64 = [base64.b64encode(foto[0]).decode('utf-8') for foto in fotos]

                return JsonResponse({
                    'success': True,
                    'fotos': fotos_base64,
                    'total_fotos': len(fotos_base64)
                })

        except Exception as e:
            print(f"Erro ao carregar fotos: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'error': 'Método não permitido'}, status=405)

@login_required
@csrf_exempt
def pesquisar_pedido(request):
    if request.method == 'GET':
        # Retorna o template HTML para a página de recebimento
        return render(request, 'recebimento.html')

    elif request.method == 'POST':
        numero_pedido = request.POST.get('numero_pedido')
        filtro_todos = request.POST.get('filtro_todos', 'false').lower() == 'true'
        try:
            with connections['doran'].cursor() as cursor:
                # Filtro opcional por status
                filtro_status = ""
                if not filtro_todos:
                    filtro_status = """
                            AND RTRIM(TB_STATUS_PEDIDO_COMPRA.DESCRICAO_STATUS_PEDIDO_COMPRA) IN (
                                'PRODUTO EM TRÂNSITO PARCIAL DIV',
                                'PRODUTO EM TRÂNSITO PARCIAL',
                                'PRODUTO EM TRÂNSITO DIVERGENTE',
                                'PRODUTO EM TRANSITO',
                                'ENTREGA CONF. FORNECEDOR'
                            )
                            """

                query = f"""
                        SELECT 
                        TB_PEDIDO_COMPRA.NUMERO_PEDIDO_COMPRA,
                        TB_PEDIDO_COMPRA.NUMERO_ITEM_COMPRA,
                        ID_PRODUTO_COMPRA,
                        RTRIM(CODIGO_PRODUTO_COMPRA) AS CODIGO_PRODUTO_COMPRA,
                        RTRIM(TB_PRODUTO.DESCRICAO_PRODUTO) AS DESCRICAO_PRODUTO,
                        CONVERT(FLOAT, QTDE_ITEM_COMPRA) AS QTDE_ITEM_COMPRA,
                        CONVERT(FLOAT, QTDE_RECEBIDA) AS QTDE_RECEBIDA,
                        CONVERT(DATE, PREVISAO_ENTREGA_ITEM_COMPRA) AS PREVISAO_ENTREGA_ITEM_COMPRA,
                        RTRIM(TB_FORNECEDOR.NOME_FANTASIA_FORNECEDOR) AS NOME_FANTASIA_FORNECEDOR,
                        RTRIM(TB_STATUS_PEDIDO_COMPRA.DESCRICAO_STATUS_PEDIDO_COMPRA) AS DESCRICAO_STATUS_PEDIDO_COMPRA,
                        TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_PEDIDO_VENDA,
                        RTRIM(TB_PEDIDO_COMPRA.UNIDADE_ITEM_COMPRA) AS UNIDADE_ITEM_COMPRA,
                        RTRIM(TB_LOCAL.DESCRICAO_LOCAL) AS DESCRICAO_LOCAL
                        FROM TB_PEDIDO_COMPRA (NOLOCK)
                        LEFT JOIN TB_LOCAL (NOLOCK) ON TB_LOCAL.ID_LOCAL = TB_PEDIDO_COMPRA.ID_LOCAL_PROVISORIO
                        JOIN TB_PRODUTO (NOLOCK) ON TB_PRODUTO.ID_PRODUTO = TB_PEDIDO_COMPRA.ID_PRODUTO_COMPRA
                        JOIN TB_FORNECEDOR (NOLOCK) ON TB_FORNECEDOR.CODIGO_FORNECEDOR = TB_PEDIDO_COMPRA.CODIGO_FORNECEDOR
                        JOIN TB_STATUS_PEDIDO_COMPRA (NOLOCK) ON TB_STATUS_PEDIDO_COMPRA.CODIGO_STATUS_COMPRA = TB_PEDIDO_COMPRA.STATUS_ITEM_COMPRA
                        LEFT JOIN TB_ASSOCIACAO_COMPRA_VENDA (NOLOCK) ON TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_PEDIDO_COMPRA = TB_PEDIDO_COMPRA.NUMERO_PEDIDO_COMPRA AND TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_ITEM_COMPRA = TB_PEDIDO_COMPRA.NUMERO_ITEM_COMPRA
                        WHERE TB_PEDIDO_COMPRA.CODIGO_FORNECEDOR != 2
                        AND TB_PEDIDO_COMPRA.NUMERO_PEDIDO_COMPRA = %s
                        {filtro_status}
                        ORDER BY CONVERT(DATE, PREVISAO_ENTREGA_ITEM_COMPRA) ASC
                        """

                cursor.execute(query, [int(numero_pedido)])
                itens = cursor.fetchall()

            data = {
                'success': True,
                'pedidos': []
            }

            for item in itens:
                with connections['doran'].cursor() as cursor:
                    cursor.execute("""
                        SELECT COUNT(*) 
                        FROM TB_FOTO_RECEBIMENTO 
                        WHERE NUMERO_PEDIDO_COMPRA = %s AND NUMERO_ITEM_COMPRA = %s
                    """, [int(item[0]), int(item[1])])
                    total_fotos = cursor.fetchone()[0]

                data['pedidos'].append({
                    'id': item[1],
                    'codigo': item[3],
                    'descricao': item[4],
                    'quantidade': item[5],
                    'data_entrega': item[7].strftime('%d/%m/%Y'),
                    'fornecedor': item[8],
                    'status': item[9],
                    'fotos': total_fotos,
                    'pv': item[10] if item[10] else '',
                    'destino': item[12] if item[12] else '',
                    'unidade_medida': item[11]
                })

            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erro ao consultar pedidos: {str(e)}'})

    return JsonResponse({'success': False, 'message': 'Método inválido'})

@login_required
@csrf_exempt
def pesquisar_pedido_v2(request):
    # Esta é a versão v2 da view, que renderiza o template 'recebimento_v2.html'.
    # Diferente da versão anterior, nesta os links das bibliotecas (CSS/JS) são carregados de fontes externas (CDNs),
    # e não a partir dos arquivos locais (static).
    if request.method == 'GET':
        # Retorna o template HTML para a página de recebimento
        return render(request, 'recebimento_v2.html')

    elif request.method == 'POST':
        numero_pedido = request.POST.get('numero_pedido')
        filtro_todos = request.POST.get('filtro_todos', 'false').lower() == 'true'
        try:
            with connections['doran'].cursor() as cursor:
                # Filtro opcional por status
                filtro_status = ""
                if not filtro_todos:
                    filtro_status = """
                            AND RTRIM(TB_STATUS_PEDIDO_COMPRA.DESCRICAO_STATUS_PEDIDO_COMPRA) IN (
                                'PRODUTO EM TRÂNSITO PARCIAL DIV',
                                'PRODUTO EM TRÂNSITO PARCIAL',
                                'PRODUTO EM TRÂNSITO DIVERGENTE',
                                'PRODUTO EM TRANSITO',
                                'ENTREGA CONF. FORNECEDOR'
                            )
                            """

                query = f"""
                        SELECT 
                        TB_PEDIDO_COMPRA.NUMERO_PEDIDO_COMPRA,
                        TB_PEDIDO_COMPRA.NUMERO_ITEM_COMPRA,
                        ID_PRODUTO_COMPRA,
                        RTRIM(CODIGO_PRODUTO_COMPRA) AS CODIGO_PRODUTO_COMPRA,
                        RTRIM(TB_PRODUTO.DESCRICAO_PRODUTO) AS DESCRICAO_PRODUTO,
                        CONVERT(FLOAT, QTDE_ITEM_COMPRA) AS QTDE_ITEM_COMPRA,
                        CONVERT(FLOAT, QTDE_RECEBIDA) AS QTDE_RECEBIDA,
                        CONVERT(DATE, PREVISAO_ENTREGA_ITEM_COMPRA) AS PREVISAO_ENTREGA_ITEM_COMPRA,
                        RTRIM(TB_FORNECEDOR.NOME_FANTASIA_FORNECEDOR) AS NOME_FANTASIA_FORNECEDOR,
                        RTRIM(TB_STATUS_PEDIDO_COMPRA.DESCRICAO_STATUS_PEDIDO_COMPRA) AS DESCRICAO_STATUS_PEDIDO_COMPRA,
                        TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_PEDIDO_VENDA,
                        RTRIM(TB_PEDIDO_COMPRA.UNIDADE_ITEM_COMPRA) AS UNIDADE_ITEM_COMPRA,
                        RTRIM(TB_LOCAL.DESCRICAO_LOCAL) AS DESCRICAO_LOCAL
                        FROM TB_PEDIDO_COMPRA (NOLOCK)
                        LEFT JOIN TB_LOCAL (NOLOCK) ON TB_LOCAL.ID_LOCAL = TB_PEDIDO_COMPRA.ID_LOCAL_PROVISORIO
                        JOIN TB_PRODUTO (NOLOCK) ON TB_PRODUTO.ID_PRODUTO = TB_PEDIDO_COMPRA.ID_PRODUTO_COMPRA
                        JOIN TB_FORNECEDOR (NOLOCK) ON TB_FORNECEDOR.CODIGO_FORNECEDOR = TB_PEDIDO_COMPRA.CODIGO_FORNECEDOR
                        JOIN TB_STATUS_PEDIDO_COMPRA (NOLOCK) ON TB_STATUS_PEDIDO_COMPRA.CODIGO_STATUS_COMPRA = TB_PEDIDO_COMPRA.STATUS_ITEM_COMPRA
                        LEFT JOIN TB_ASSOCIACAO_COMPRA_VENDA (NOLOCK) ON TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_PEDIDO_COMPRA = TB_PEDIDO_COMPRA.NUMERO_PEDIDO_COMPRA AND TB_ASSOCIACAO_COMPRA_VENDA.NUMERO_ITEM_COMPRA = TB_PEDIDO_COMPRA.NUMERO_ITEM_COMPRA
                        WHERE TB_PEDIDO_COMPRA.CODIGO_FORNECEDOR != 2
                        AND TB_PEDIDO_COMPRA.NUMERO_PEDIDO_COMPRA = %s
                        {filtro_status}
                        ORDER BY CONVERT(DATE, PREVISAO_ENTREGA_ITEM_COMPRA) ASC
                        """

                cursor.execute(query, [int(numero_pedido)])
                itens = cursor.fetchall()

            data = {
                'success': True,
                'pedidos': []
            }

            for item in itens:
                with connections['doran'].cursor() as cursor:
                    cursor.execute("""
                        SELECT COUNT(*) 
                        FROM TB_FOTO_RECEBIMENTO 
                        WHERE NUMERO_PEDIDO_COMPRA = %s AND NUMERO_ITEM_COMPRA = %s
                    """, [int(item[0]), int(item[1])])
                    total_fotos = cursor.fetchone()[0]

                data['pedidos'].append({
                    'id': item[1],
                    'codigo': item[3],
                    'descricao': item[4],
                    'quantidade': item[5],
                    'data_entrega': item[7].strftime('%d/%m/%Y'),
                    'fornecedor': item[8],
                    'status': item[9],
                    'fotos': total_fotos,
                    'pv': item[10] if item[10] else '',
                    'destino': item[12] if item[12] else '',
                    'unidade_medida': item[11]
                })

            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erro ao consultar pedidos: {str(e)}'})

    return JsonResponse({'success': False, 'message': 'Método inválido'})