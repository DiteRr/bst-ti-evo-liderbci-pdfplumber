import mysql.connector
import datetime
from helpers import fecha_actual_str
import logging

logger = logging.getLogger(__name__)

# 🔹 CONEXIÓN HARDCODEADA
def obtener_conexion():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="polo1234prince",
        database="textract",
        port=3306
    )

# ==========================================================
# INSERTAR EECC NACIONAL
# ==========================================================

def insertar_eecc_nacional(lista_datos):
    conn = obtener_conexion()
    cursor = conn.cursor()

    for datos in lista_datos:

        query = """
            INSERT INTO EECC_Nacional_T (
                CodigoBarraSectorizacion, Nombre, Direccion, Comuna, Region, NumeroTarjeta,
                FechaEstadoCuenta, Kw_CupoTotal, Kw_CupoUtilizado, Kw_CupoDisponible,
                Kw_CupoTotal1, Kw_CupoUtilizado1, Kw_CupoDisponible1,
                Kw_CupoTotal2, Kw_CupoUtilizado2, Kw_CupoDisponible2, 
                TasaInteresVigenteRefundido, TasaInteresVigenteCuotas, TasaInteresVigenteAvance,
                CAERefundido, CAECuotas, CAEAvance, CAEPrepago,
                PeriodoFacturadoDesde, PeriodoFacturadoHasta, PagarHasta,
                PeriodoAnteriorDesde, PeriodoAnteriorHasta,
                SaldoAdeudadoInicioPeriodoAnterior, MontoFacturadoPeriodoAnterior,
                MontoPagadoPeriodoAnterior, SaldoAdeudadoFinalPeriodoAnterior,
                MontoTotalFacturado, MontoMinimoPagar, CostoMonetarioPrepago,
                VencimientoActual, Mes1, Mes2, Mes3, Mes4,
                ProximoPeriodoFacturacionDesde, ProximoPeriodoFacturacionHasta,
                GastosDeCobranza, InteresMoratorio,
                Codigo_producto, NOMBRE_ARCHIVO, Lote, Sector_Cuartel, TextoLiberacion, CodigoPostal
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        valores = (
            datos.get('CodigoBarraSectorizacion'),
            datos.get('Nombre'),
            datos.get('Direccion'),
            datos.get('Comuna'),
            datos.get('Region'),
            datos.get('NumeroTarjeta'),
            datos.get('FechaEstadoCuenta'),
            datos.get('CupoTotal'),
            datos.get('CupoUtilizado'),
            datos.get('CupoDisponible'),
            datos.get('CupoAvanceTotal'),
            datos.get('CupoAvanceUtilizado'),
            datos.get('CupoAvanceDisponible'),
            datos.get('CupoSATotal'),
            datos.get('CupoSAUtilizado'),
            datos.get('CupoSADisponible'),
            datos.get('TasaInteres1'),
            datos.get('TasaInteres2'),
            datos.get('TasaInteres3'),
            datos.get('CAE1'),
            datos.get('CAE2'),
            datos.get('CAE3'),
            datos.get('CAE_PREPAGO'),
            datos.get('PeriodoFacturadoDesde'),
            datos.get('PeriodoFacturadoHasta'),
            datos.get('FechaPagoHasta'),
            datos.get('PeriodoDeFacturacionAnteriorDesde'),
            datos.get('PeriodoDeFacturacionAnteriorHasta'),
            datos.get('SaldoAdeudadoInicioPeriodoAnterior'),
            datos.get('MontoFacturadoPeriodoAnterior'),
            datos.get('MontoPagadoPeriodoAnterior'),
            datos.get('SaldoAdeudadoFinalPeriodoAnterior'),
            datos.get('MontoTotalFacturado'),
            datos.get('MontoMinimoAPagar'),
            datos.get('CostoMonetarioPrepago'),
            datos.get('VencimientoActual'),
            datos.get('Mes1'),
            datos.get('Mes2'),
            datos.get('Mes3'),
            datos.get('Mes4'),
            datos.get('ProximoPeriodoFacturadoDesde'),
            datos.get('ProximoPeriodoFacturadoHasta'),
            datos.get('GastosCobranza'),
            datos.get('InteresMoratorio'),
            datos.get('Codigo_producto'),
            datos.get('NOMBRE_ARCHIVO'),
            fecha_actual_str(),
            datos.get('Sector_Cuartel'),
            datos.get('TextoLiberacion'),
            datos.get('CodigoPostal')
        )

        cursor.execute(query, valores)

        # 🔹 Obtener ID generado (equivalente a SCOPE_IDENTITY())
        row_index_nacional = cursor.lastrowid

        lista_ops = datos.get('Operaciones', [])
        if lista_ops:
            _insertar_total_operaciones(cursor, row_index_nacional, lista_ops)

    conn.commit()
    cursor.close()
    conn.close()

# ==========================================================
# INSERTAR TOTAL OPERACIONES
# ==========================================================

def _insertar_total_operaciones(cursor, row_index, lista_ops):

    query = """
        INSERT INTO TOTAL_OPERACIONES_T (
            EECC_Nacional_ROW_INDEX,
            LugarOperacion,
            FechaOperacion,
            DescripOperacion,
            MontoOperacion,
            MontoTotal,
            NroCuota,
            ValorCuotaMensual
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    for op in lista_ops:
        cursor.execute(query, (
            row_index,
            op.get('LugarOperacion'),
            op.get('FechaOperacion'),
            op.get('DescripOperacion'),
            op.get('MontoOperacion'),
            op.get('MontoTotal'),
            op.get('NroCuota'),
            op.get('ValorCuotaMensual')
        ))

# ==========================================================
# INSERTAR EECC INTERNACIONAL
# ==========================================================

def insertar_eecc_internacional(lista_datos):
    conn = obtener_conexion()
    cursor = conn.cursor()

    for datos in lista_datos:

        query = """
            INSERT INTO EECC_Internacional_T (
                CodigoBarraSectorizacion, Nombre, Direccion, Comuna, Region, NumeroTarjeta,
                FechaEstadoCuenta, CupoTotalUSD, CupoUtilizadoUSD, CupoDisponibleUSD,
                PeriodoFacturadoDesde, PeriodoFacturadoHasta,
                SaldoAnteriorFacturadoUSD, AbonoRealizadoUSD,
                TraspasoDeudaNacionalUSD, DeudaTotalFacturadaDelMesUSD, PagarHasta,
                Nombre1, NumeroDeCuenta, PagarHasta1,
                MontoTotalFacturado, Nombre2, NumeroDeCuenta1, PagarHasta2,
                MontoTotalFacturado1, Codigo_producto, NOMBRE_ARCHIVO, Lote, CodigoPostal
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(query, (
            datos.get('CodigoBarraSectorizacion'),
            datos.get('Nombre'),
            datos.get('Direccion'),
            datos.get('Comuna'),
            datos.get('Region'),
            datos.get('NumeroTarjeta'),
            datos.get('FechaEstadoCuenta'),
            datos.get('CupoTotalUSD'),
            datos.get('CupoUtilizadoUSD'),
            datos.get('CupoDisponibleUSD'),
            datos.get('PeriodoFacturadoDesde'),
            datos.get('PeriodoFacturadoHasta'),
            datos.get('SaldoAnteriorFacturadoUS'),
            datos.get('AbonoRealizadoUS'),
            datos.get('TraspasoDeudaNacionalUS'),
            datos.get('DeudaTotalFacturadaMesUS'),
            datos.get('FechaPagoHasta'),
            datos.get('Nombre'),
            datos.get('NumeroDeCuenta'),
            datos.get('FechaPagoHasta'),
            datos.get('DeudaTotalFacturadaMesUS'),
            datos.get('Nombre'),
            datos.get('NumeroDeCuenta'),
            datos.get('FechaPagoHasta'),
            datos.get('DeudaTotalFacturadaMesUS'),
            datos.get('Codigo_producto'),
            datos.get('NOMBRE_ARCHIVO'),
            datetime.datetime.now().strftime("%Y-%m-%d"),
            datos.get('CodigoPostal')
        ))

        row_index_generado = cursor.lastrowid

        lista_transacciones = datos.get('Transacciones', [])
        if lista_transacciones:
            _insertar_transacciones_internacionales(cursor, row_index_generado, lista_transacciones)

    conn.commit()
    cursor.close()
    conn.close()

# ==========================================================
# INSERTAR TRANSACCIONES INTERNACIONALES
# ==========================================================

def _insertar_transacciones_internacionales(cursor, row_index, lista_transacciones):

    query = """
        INSERT INTO Transacciones_T (
            EECC_Internacional_ROW_INDEX,
            NumeroReferenciaInternacional,
            FechaOperacion,
            DescripcionOperacionOCobro,
            Ciudad,
            Pais,
            MontoMoneda,
            MontoUSD
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    for t in lista_transacciones:
        cursor.execute(query, (
            row_index,
            t.get('NumeroReferenciaInternacional'),
            t.get('FechaOperacion'),
            t.get('DescripcionOperacionOCobro'),
            t.get('Ciudad'),
            t.get('Pais'),
            t.get('MontoMoneda'),
            t.get('MontoUSD')
        ))
