# -*- coding: utf-8 -*-

"""
***************************************************************************
    PointDistance.py
    ---------------------
    Date                 : August 2012
    Copyright            : (C) 2012 by Victor Olaya
    Email                : volayaf at gmail dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
from builtins import next
from builtins import str
from builtins import range

__author__ = 'Victor Olaya'
__date__ = 'August 2012'
__copyright__ = '(C) 2012, Victor Olaya'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
import math

from qgis.PyQt.QtGui import QIcon

from qgis.core import QgsFeatureRequest, QgsDistanceArea, QgsProcessingUtils

from processing.core.GeoAlgorithm import GeoAlgorithm
from processing.core.parameters import ParameterNumber
from processing.core.parameters import ParameterVector
from processing.core.parameters import ParameterSelection
from processing.core.parameters import ParameterTableField
from processing.core.outputs import OutputTable
from processing.tools import dataobjects

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class PointDistance(GeoAlgorithm):

    INPUT_LAYER = 'INPUT_LAYER'
    INPUT_FIELD = 'INPUT_FIELD'
    TARGET_LAYER = 'TARGET_LAYER'
    TARGET_FIELD = 'TARGET_FIELD'
    MATRIX_TYPE = 'MATRIX_TYPE'
    NEAREST_POINTS = 'NEAREST_POINTS'
    DISTANCE_MATRIX = 'DISTANCE_MATRIX'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'images', 'ftools', 'matrix.png'))

    def group(self):
        return self.tr('Vector analysis tools')

    def name(self):
        return 'distancematrix'

    def displayName(self):
        return self.tr('Distance matrix')

    def defineCharacteristics(self):
        self.mat_types = [self.tr('Linear (N*k x 3) distance matrix'),
                          self.tr('Standard (N x T) distance matrix'),
                          self.tr('Summary distance matrix (mean, std. dev., min, max)')]

        self.addParameter(ParameterVector(self.INPUT_LAYER,
                                          self.tr('Input point layer'), [dataobjects.TYPE_VECTOR_POINT]))
        self.addParameter(ParameterTableField(self.INPUT_FIELD,
                                              self.tr('Input unique ID field'), self.INPUT_LAYER,
                                              ParameterTableField.DATA_TYPE_ANY))
        self.addParameter(ParameterVector(self.TARGET_LAYER,
                                          self.tr('Target point layer'), dataobjects.TYPE_VECTOR_POINT))
        self.addParameter(ParameterTableField(self.TARGET_FIELD,
                                              self.tr('Target unique ID field'), self.TARGET_LAYER,
                                              ParameterTableField.DATA_TYPE_ANY))
        self.addParameter(ParameterSelection(self.MATRIX_TYPE,
                                             self.tr('Output matrix type'), self.mat_types, 0))
        self.addParameter(ParameterNumber(self.NEAREST_POINTS,
                                          self.tr('Use only the nearest (k) target points'), 0, 9999, 0))

        self.addOutput(OutputTable(self.DISTANCE_MATRIX, self.tr('Distance matrix')))

    def processAlgorithm(self, context, feedback):
        inLayer = QgsProcessingUtils.mapLayerFromString(self.getParameterValue(self.INPUT_LAYER), context)
        inField = self.getParameterValue(self.INPUT_FIELD)
        targetLayer = QgsProcessingUtils.mapLayerFromString(self.getParameterValue(self.TARGET_LAYER), context)
        targetField = self.getParameterValue(self.TARGET_FIELD)
        matType = self.getParameterValue(self.MATRIX_TYPE)
        nPoints = self.getParameterValue(self.NEAREST_POINTS)

        outputFile = self.getOutputFromName(self.DISTANCE_MATRIX)

        if nPoints < 1:
            nPoints = QgsProcessingUtils.featureCount(targetLayer, context)

        self.writer = outputFile.getTableWriter([])

        if matType == 0:
            # Linear distance matrix
            self.linearMatrix(context, inLayer, inField, targetLayer, targetField,
                              matType, nPoints, feedback)
        elif matType == 1:
            # Standard distance matrix
            self.regularMatrix(context, inLayer, inField, targetLayer, targetField,
                               nPoints, feedback)
        elif matType == 2:
            # Summary distance matrix
            self.linearMatrix(context, inLayer, inField, targetLayer, targetField,
                              matType, nPoints, feedback)

    def linearMatrix(self, context, inLayer, inField, targetLayer, targetField,
                     matType, nPoints, feedback):
        if matType == 0:
            self.writer.addRecord(['InputID', 'TargetID', 'Distance'])
        else:
            self.writer.addRecord(['InputID', 'MEAN', 'STDDEV', 'MIN', 'MAX'])

        index = QgsProcessingUtils.createSpatialIndex(targetLayer, context)

        inIdx = inLayer.fields().lookupField(inField)
        outIdx = targetLayer.fields().lookupField(targetField)

        distArea = QgsDistanceArea()

        features = QgsProcessingUtils.getFeatures(inLayer, context)
        total = 100.0 / QgsProcessingUtils.featureCount(inLayer, context)
        for current, inFeat in enumerate(features):
            inGeom = inFeat.geometry()
            inID = str(inFeat.attributes()[inIdx])
            featList = index.nearestNeighbor(inGeom.asPoint(), nPoints)
            distList = []
            vari = 0.0
            request = QgsFeatureRequest().setFilterFids(featList).setSubsetOfAttributes([outIdx])
            for outFeat in targetLayer.getFeatures(request):
                outID = outFeat.attributes()[outIdx]
                outGeom = outFeat.geometry()
                dist = distArea.measureLine(inGeom.asPoint(),
                                            outGeom.asPoint())
                if matType == 0:
                    self.writer.addRecord([inID, str(outID), str(dist)])
                else:
                    distList.append(float(dist))

            if matType != 0:
                mean = sum(distList) / len(distList)
                for i in distList:
                    vari += (i - mean) * (i - mean)
                vari = math.sqrt(vari / len(distList))
                self.writer.addRecord([inID, str(mean),
                                       str(vari), str(min(distList)),
                                       str(max(distList))])

            feedback.setProgress(int(current * total))

    def regularMatrix(self, context, inLayer, inField, targetLayer, targetField,
                      nPoints, feedback):
        index = QgsProcessingUtils.createSpatialIndex(targetLayer, context)

        inIdx = inLayer.fields().lookupField(inField)

        distArea = QgsDistanceArea()

        first = True
        features = QgsProcessingUtils.getFeatures(inLayer, context)
        total = 100.0 / QgsProcessingUtils.featureCount(inLayer, context)
        for current, inFeat in enumerate(features):
            inGeom = inFeat.geometry()
            inID = str(inFeat.attributes()[inIdx])
            featList = index.nearestNeighbor(inGeom.asPoint(), nPoints)
            if first:
                first = False
                data = ['ID']
                for i in range(len(featList)):
                    data.append('DIST_{0}'.format(i + 1))
                self.writer.addRecord(data)

            data = [inID]
            for i in featList:
                request = QgsFeatureRequest().setFilterFid(i)
                outFeat = next(targetLayer.getFeatures(request))
                outGeom = outFeat.geometry()
                dist = distArea.measureLine(inGeom.asPoint(),
                                            outGeom.asPoint())
                data.append(str(float(dist)))
            self.writer.addRecord(data)

            feedback.setProgress(int(current * total))
